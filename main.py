import os
import imaplib
from email import policy
from email.parser import BytesParser
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import html as htmllib
import streamlit as st

# ----- Helpers -----
def decode_mime(s):
    if not s:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s

def get_text_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if disp == "attachment":
                continue
            if ctype == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace")
                except Exception:
                    return payload.decode("utf-8", errors="replace")
    else:
        if msg.get_content_type() == "text/plain":
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except Exception:
                return payload.decode("utf-8", errors="replace")
    return ""

def get_html_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if disp == "attachment":
                continue
            if ctype == "text/html":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace")
                except Exception:
                    return payload.decode("utf-8", errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except Exception:
                return payload.decode("utf-8", errors="replace")
    return ""

def extract_links_from_html(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip()
        if text not in ["네, 본인입니다", "코드 받기"]:
            continue
        href = htmllib.unescape(a["href"])
        links.append((text, href))
    return links

def fetch_emails(user, pw, server, port, mailbox, criteria, limit):
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

            if subject not in ["중요: 넷플릭스 이용 가구를 업데이트하는 방법", "회원님의 넷플릭스 임시 접속 코드"]:
                continue

            html = get_html_body(msg)
            btn_links = extract_links_from_html(html)
            links = btn_links

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

# NEW: secrets-based config
def get_config():
    s = st.secrets
    return {
        "access_key": s.get("ACCESS_KEY"),
        "user": s.get("ID"),
        "pw": s.get("PW"),
        "server": s.get("SERVER"),
        "port": int(s.get("PORT")),
        "mailbox": s.get("MAILBOX"),
        "criteria": s.get("CRITERIA", "ALL"),
        "limit": int(s.get("LIMIT", 20)),
    }

# ----- UI -----
st.set_page_config(page_title="Mail Link Finder", layout="wide")
st.title("Mail Link Finder (Naver IMAP)")

with st.sidebar:
    st.header("Access")
    access_pw = st.text_input("Access Password", type="password")
    run = st.button("Fetch Links")

if run:
    cfg = get_config()
    if not cfg["access_key"]:
        st.error("ACCESS_KEY is not set in .streamlit/secrets.toml")
    elif access_pw != cfg["access_key"]:
        st.error("Access denied.")
    elif not cfg["user"] or not cfg["pw"]:
        st.error("ID/PW not configured in secrets.")
    else:
        try:
            with st.spinner("Fetching emails..."):
                rows = fetch_emails(
                    user=cfg["user"],
                    pw=cfg["pw"],
                    server=cfg["server"],
                    port=cfg["port"],
                    mailbox=cfg["mailbox"],
                    criteria=cfg["criteria"],
                    limit=cfg["limit"],
                )

            # sort by date desc
            def key_dt(r):
                dt = r.get("dt")
                return dt or datetime.min.replace(tzinfo=timezone.utc)
            rows.sort(key=key_dt, reverse=True)

            # optional: only messages with links
            rows = [r for r in rows if r.get("links")]

            # quick links aggregate
            all_links = []
            for r in rows:
                for text, href in r.get("links", []):
                    all_links.append((text or "(no text)", href, r["subject"], r.get("dt")))

            st.success(f"Collected {len(all_links)} link(s) from {len(rows)} email(s).")

            if not all_links:
                st.info("No matching links.")
            else:
                st.subheader("Quick Links")
                today_local = datetime.now().astimezone().date()
                for label, href, subj, dt in all_links:
                    is_today = bool(dt and dt.astimezone().date() == today_local)
                    star = "⭐ " if is_today else ""
                    st.markdown(f'- {star}[{label}]({href}) — {subj}')

                # details (optional)
                st.divider()
                st.caption("Details")
                for r in rows:
                    dt = r.get("dt")
                    is_today = bool(dt and dt.astimezone().date() == today_local)
                    header = f'#{r["uid"]} | {r["date"]} | {r["subject"]}'
                    if is_today:
                        header = f'⭐ TODAY | {header}'
                    with st.expander(header, expanded=is_today):
                        st.text(f'From: {r["from"]}')
                        st.text(f'Snippet: {r["snippet"]}')
                        links = r.get("links", [])
                        if links:
                            for text, href in links[:20]:
                                label = text if text else "(no text)"
                                st.markdown(f'- [{label}]({href})')
                        else:
                            st.caption("No matching links.")
        except Exception as e:
            st.error(f"Error: {e}")