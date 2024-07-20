import smtplib
import csv, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid
from time import sleep
import dotenv

dotenv.load_dotenv()


def send_emails(
    csv_file, subject, text_body: str = None, html_body: str = None, attachments=None
):
    smtp_server = os.getenv("SMTP_SERVER")
    domain = os.getenv("SMTP_DOMAIN")
    smtp_port = int(os.getenv("SMTP_PORT"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    full_name = os.getenv("SMTP_FULL_NAME")

    with open(csv_file, newline="") as file:
        reader = csv.DictReader(file)
        contacts = [(row["email"], row["name"]) for row in reader]

    server = smtplib.SMTP_SSL(host=smtp_server, port=smtp_port)
    server.login(username, password)
    
    for email, name in contacts:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = full_name
        msg["To"] = email
        msg["Date"] = formatdate(localtime=True)
        msg["message-id"] = make_msgid(domain=domain)

        if text_body or html_body:
            alt_part = MIMEMultipart("alternative")
            msg.attach(alt_part)

            if text_body:
                alt_part.attach(MIMEText(text_body.replace("{{name}}", name), "plain"))

            if html_body:
                alt_part.attach(MIMEText(html_body.replace("{{name}}", name), "html"))

        if attachments:
            for file_path in attachments:
                with open(file_path, "rb") as f:
                    file_data = MIMEApplication(
                        f.read(), Name=os.path.basename(file_path)
                    )
                file_data["Content-Disposition"] = (
                    f'attachment; filename="{os.path.basename(file_path)}"'
                )
                msg.attach(file_data)

        server.send_message(msg)
        print(f"Email sent to {name} at {email}")
        sleep(2)


if __name__ == "__main__":
    csv_file = "contacts.csv"
    subject = os.getenv("EMAIL_SUBJECT")
    html_body = open("email.html").read()
    text_body = open("email.txt").read()

    send_emails(csv_file, subject, text_body, html_body)
