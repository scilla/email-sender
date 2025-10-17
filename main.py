import os
import csv
import re
import smtplib
import string
import hashlib
from time import sleep
from email.utils import formatdate, make_msgid, formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import dotenv

dotenv.load_dotenv()

PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")

def _split_full_name(full_name: str | None) -> tuple[str | None, str | None]:
    """
    Split a full name by spaces. Last token = last name, the rest = first name.
    Handles extra spaces. If only one token: it's the first name.
    """
    if not full_name:
        return None, None
    tokens = [t for t in full_name.strip().split() if t]
    if not tokens:
        return None, None
    if len(tokens) == 1:
        return tokens[0], None
    first = " ".join(tokens[:-1])
    last = tokens[-1]
    return first, last

def _gen_random_id(first_name: str | None, last_name: str | None, email: str, n: int = 10) -> str:
    """Derive a stable identifier from name + email for consistent personalization."""
    components = [
        (first_name or "").strip().lower(),
        (last_name or "").strip().lower(),
        (email or "").strip().lower(),
    ]
    seed = "|".join(components)
    digest = hashlib.sha256(seed.encode("utf-8")).digest()

    alphabet = string.ascii_uppercase + string.digits
    chars: list[str] = []
    pool = digest

    while len(chars) < n:
        for b in pool:
            chars.append(alphabet[b % len(alphabet)])
            if len(chars) == n:
                break
        else:
            pool = hashlib.sha256(pool).digest()

    return "".join(chars)

def _render_template(template: str, data: dict) -> str:
    """
    Replace {{Key}} with values from data (stringified).
    Missing keys -> empty string.
    """
    def repl(match):
        key = match.group(1)
        val = data.get(key, "")
        return "" if val is None else str(val)
    return PLACEHOLDER_RE.sub(repl, template)

def _build_credited_events_list(raw: str | None) -> str:
    """
    Turn a delimited string into HTML <li> items.
    Accepts '|' or ';' as separators.
    """
    if not raw:
        return ""
    parts = [p.strip().replace('from 09:00 (I Cheer)', 'from 08:45 (Cheering Point)') for p in re.split(r"[|;]", raw) if p.strip()]
    return "".join(f"<li>{p}</li>" for p in parts)

def send_emails(
    csv_file: str,
    subject: str,
    text_body: str | None = None,
    html_body: str | None = None,
    attachments: list[str] | None = None,
    sleep_seconds: float = 5.0,
):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    full_name_from = os.getenv("SMTP_FULL_NAME", "")
    smtp_domain = os.getenv("SMTP_DOMAIN", None)
    reply_to = os.getenv("SMTP_REPLY_TO", "")  # optional

    if not all([smtp_server, smtp_port, username, password]):
        raise RuntimeError("Missing SMTP env vars (SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD).")

    # Load contacts
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Expect headers: full-name,email,events
        rows = list(reader)

    # Open SMTP (SSL by default)
    server = smtplib.SMTP_SSL(host=smtp_server, port=smtp_port)
    try:
        server.login(username, password)
        input(f"Press Enter to start sending emails to {len(rows)} contacts...")
        for row in rows:
            email = (row.get("email") or "").strip()
            full_name_raw = (row.get("full-name") or "").strip()
            events_raw = (row.get("events") or "").strip()

            if not email:
                print("Skipped a row without 'email'.")
                continue

            # Split name into FirstName / LastName
            first_name, last_name = _split_full_name(full_name_raw)

            # Prepare render data (keep original keys + normalized keys)
            data = dict(row)  # start with original
            data["FirstName"] = first_name or ""
            data["LastName"] = last_name or ""
            data["name"] = full_name_raw  # back-compat for {{name}}
            data["full-name"] = full_name_raw  # in case you use {{full-name}}

            # Ensure RandomID
            data["RandomID"] = data.get("RandomID") or _gen_random_id(first_name, last_name, email)

            # Build credited events HTML
            data["CreditedEventsList"] = _build_credited_events_list(events_raw)

            # Prepare message
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = formataddr((full_name_from, username)) if full_name_from else username
            msg["To"] = email
            if reply_to:
                msg["Reply-To"] = reply_to
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=smtp_domain)

            # Alternatives (text/plain + text/html)
            if text_body or html_body:
                alt = MIMEMultipart("alternative")
                msg.attach(alt)

                if text_body:
                    rendered_text = _render_template(text_body, data)
                    alt.attach(MIMEText(rendered_text, "plain", "utf-8"))

                if html_body:
                    rendered_html = _render_template(html_body, data)
                    alt.attach(MIMEText(rendered_html, "html", "utf-8"))

            # Attach files
            if attachments:
                for file_path in attachments:
                    with open(file_path, "rb") as fh:
                        part = MIMEApplication(fh.read(), Name=os.path.basename(file_path))
                    part["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'
                    msg.attach(part)

            server.send_message(msg)
            display = full_name_raw or email
            print(f"Email sent to {display} <{email}>")
            sleep(sleep_seconds)
    finally:
        try:
            server.quit()
        except Exception:
            pass

if __name__ == "__main__":
    csv_file = os.getenv("EMAIL_CSV_FILE", "contacts.csv")
    subject = os.getenv("EMAIL_SUBJECT", "ROR10 · BtG Rome Weekend — Your Pass & Schedule")

    # Load bodies
    with open("email.html", "r", encoding="utf-8") as f:
        html_body = f.read()
    text_body_path = "email.txt"
    if os.path.exists(text_body_path):
        with open(text_body_path, "r", encoding="utf-8") as f:
            text_body = f.read()
    else:
        text_body = (
            "ROR10 — Your pass & schedule\n\n"
            "Hi {{FirstName}} {{LastName}},\n"
            "Open the HTML version to view your personalized pass and credited events.\n"
        )

    send_emails(csv_file, subject, text_body=text_body, html_body=html_body)
