from dotenv import load_dotenv
import os
import imaplib
from email import policy
from email.parser import BytesParser
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import html as htmllib
from main import (
    decode_mime,
    get_text_body,
    get_html_body,
    extract_links_from_html,
)

def fetch_emails(user, pw, server, port, mailbox, criteria, limit, only_include_text=None, link_text_filter=None, link_href_filter=None):
    imap = imaplib.IMAP4_SSL(server, port=port)
    imap.login(user, pw)
    out = []
    try:
        rv, _ = imap.select(mailbox)
        if rv != "OK":
            raise RuntimeError(f"Failed to open mailbox: {mailbox}")

        rv, data = imap.search(None, criteria)
        if rv != "OK" or not data or not data[0]:
            return out

        ids = data[0].split()
        for num in reversed(ids[-limit:]):
            rv, msg_data = imap.fetch(num, "(RFC822)")
            if rv != "OK":
                continue
            msg = BytesParser(policy=policy.default).parsebytes(msg_data[0][1])
            subject = decode_mime(msg.get("Subject"))
            from_ = decode_mime(msg.get("From"))
            date_hdr = msg.get("Date")
            date_str = decode_mime(date_hdr)

            # parse date -> datetime (tz-aware if possible)
            dt = None
            try:
                dt = parsedate_to_datetime(date_hdr)
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = None

            text = get_text_body(msg).strip().replace("\r", " ").replace("\n", " ")
            if only_include_text and only_include_text not in text:
                continue

            html = get_html_body(msg)
            btn_links = extract_links_from_html(html, text_contains=link_text_filter) if link_text_filter else []
            nf_links = extract_links_from_html(html, href_contains=link_href_filter) if link_href_filter else []
            links = btn_links or nf_links

            snippet = text[:200] + ("..." if len(text) > 200 else "")
            out.append({
                "uid": num.decode(),
                "date": date_str,
                "dt": dt,
                "from": from_,
                "subject": subject,
                "snippet": snippet,
                "links": links
            })
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return out

# ----- Credentials -----
ACCESS_KEY = "김승현 멍청함 ㄹㅇ"

# IMAP credentials
ID = "dddooong2000@naver.com"
PW = "Chan0thug!"

# IMAP settings
SERVER = "imap.naver.com"
PORT = 993
MAILBOX = "Netflix"
CRITERIA = "ALL"
LIMIT = 20

# Filters to find the code button/link
ONLY_INCLUDE_TEXT = "이용 가구를 업데이트"
LINK_TEXT_FILTER = "네, 본인입니다"
LINK_HREF_FILTER = "netflix.com"

# get 10 latest emails from mailbox
emails = fetch_emails(
    user=ID,
    pw=PW,
    server=SERVER,
    port=PORT,
    mailbox=MAILBOX,
    criteria=CRITERIA,
    limit=LIMIT,
    only_include_text=ONLY_INCLUDE_TEXT,
    link_text_filter=LINK_TEXT_FILTER,
    link_href_filter=LINK_HREF_FILTER
)

print(emails)