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

# ----- Settings -----
DEFAULT_SERVER = "imap.naver.com"
DEFAULT_PORT = 993
DEFAULT_MAILBOX = "Netflix"  # 필요시 INBOX로 바꾸세요

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

def extract_links_from_html(html, text_contains=None, href_contains=None):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip()
        href = htmllib.unescape(a["href"])
        if text_contains and text_contains not in text:
            continue
        if href_contains and href_contains not in href:
            continue
        links.append((text, href))
    return links

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

# NEW: secrets-based config
def get_config():
    s = st.secrets
    return {
        "access_key": s.get("ACCESS_KEY", ""),
        "user": s.get("ID"),
        "pw": s.get("PW"),
        "server": s.get("SERVER", DEFAULT_SERVER),
        "port": int(s.get("PORT", DEFAULT_PORT)),
        "mailbox": s.get("MAILBOX", DEFAULT_MAILBOX),
        "criteria": s.get("CRITERIA", "ALL"),
        "limit": int(s.get("LIMIT", 20)),
        "only_include_text": s.get("ONLY_INCLUDE_TEXT") or None,
        "link_text_filter": s.get("LINK_TEXT_FILTER") or None,
        "link_href_filter": s.get("LINK_HREF_FILTER") or None,
        "only_with_links": bool(s.get("ONLY_WITH_LINKS", True)),
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
                    only_include_text=cfg["only_include_text"],
                    link_text_filter=cfg["link_text_filter"],
                    link_href_filter=cfg["link_href_filter"],
                )

            # sort by date desc
            def key_dt(r):
                dt = r.get("dt")
                return dt or datetime.min.replace(tzinfo=timezone.utc)
            rows.sort(key=key_dt, reverse=True)

            # optional: only messages with links
            if cfg["only_with_links"]:
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