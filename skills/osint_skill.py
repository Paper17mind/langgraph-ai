import os
import sys
import socket
import concurrent.futures
import requests
from langchain.tools import tool
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# Add root directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_helper import truncate_or_save

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@tool
def lookup_ip_info(ip_or_domain: str) -> str:
    """
    Perform OSINT Geo-IP & Network lookup for an IP address or domain name.
    Returns geographical location, ISP, ASN, coordinates, and proxy/hosting flag.
    """
    target = ip_or_domain.strip().replace("http://", "").replace("https://", "").split("/")[0]
    try:
        target_ip = socket.gethostbyname(target)
    except Exception as e:
        return f"Error resolving hostname '{target}': {e}"

    try:
        res = requests.get(
            f"http://ip-api.com/json/{target_ip}?fields=status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query,proxy,hosting",
            headers=HEADERS,
            timeout=10
        )
        data = res.json()
        if data.get("status") != "success":
            return f"❌ Failed to retrieve IP info: {data.get('message')}"

        output = (
            f"🌐 **IP OSINT Report**: `{data.get('query')}`\n"
            f"• Target Input: `{ip_or_domain}`\n"
            f"• Country / City: {data.get('country')}, {data.get('city')} ({data.get('regionName')})\n"
            f"• Coordinates: {data.get('lat')}, {data.get('lon')} (Google Maps: https://maps.google.com/?q={data.get('lat')},{data.get('lon')})\n"
            f"• ISP / Org: {data.get('isp')} / {data.get('org')}\n"
            f"• ASN: {data.get('as')}\n"
            f"• Proxy/VPN/Hosting: {'Yes (Risk Detected)' if data.get('proxy') or data.get('hosting') else 'No (Residential/Standard)'}\n"
        )
        return output
    except Exception as e:
        return f"Error looking up IP info: {e}"

@tool
def lookup_dns_records(domain: str) -> str:
    """
    Perform OSINT DNS lookup (A, AAAA, MX, TXT, NS, CNAME) for a target domain.
    """
    clean_domain = domain.strip().replace("http://", "").replace("https://", "").split("/")[0]
    record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]
    results = []

    # Attempt via dnspython if installed, fallback to Google DoH API
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3
        resolver.lifetime = 3

        for r_type in record_types:
            try:
                answers = resolver.resolve(clean_domain, r_type)
                vals = [str(r.to_text()) for r in answers]
                if vals:
                    results.append(f"**{r_type}**: " + ", ".join(vals))
            except Exception:
                pass
    except ImportError:
        pass

    if not results:
        # Fallback to Google DNS over HTTPS API
        for r_type in record_types:
            try:
                r = requests.get(f"https://dns.google/resolve?name={clean_domain}&type={r_type}", timeout=4)
                if r.status_code == 200:
                    data = r.json()
                    answers = data.get("Answer", [])
                    vals = [a.get("data") for a in answers if a.get("data")]
                    if vals:
                        results.append(f"**{r_type}**: " + ", ".join(vals))
            except Exception:
                pass

    if not results:
        return f"No DNS records found for `{clean_domain}`."

    output = f"📡 **DNS Records for `{clean_domain}`**:\n" + "\n".join(results)
    return truncate_or_save(output, max_length=1500, context_name="dns_lookup")

@tool
def lookup_whois_info(domain: str) -> str:
    """
    Perform WHOIS lookup for a target domain (registrar, creation/expiration dates, name servers).
    """
    clean_domain = domain.strip().replace("http://", "").replace("https://", "").split("/")[0]

    # Try python-whois package first
    try:
        import whois
        w = whois.whois(clean_domain)
        if w and (w.domain_name or w.registrar):
            creation = w.creation_date[0] if isinstance(w.creation_date, list) else w.creation_date
            expiration = w.expiration_date[0] if isinstance(w.expiration_date, list) else w.expiration_date
            ns = w.name_servers if isinstance(w.name_servers, list) else [w.name_servers]
            ns_str = ", ".join([str(s).lower() for s in ns if s]) if ns else "N/A"

            output = (
                f"📋 **WHOIS Report for `{clean_domain}`**:\n"
                f"• Registrar: {w.registrar or 'N/A'}\n"
                f"• Created Date: {creation or 'N/A'}\n"
                f"• Expiration Date: {expiration or 'N/A'}\n"
                f"• Registrant Org: {w.org or 'N/A'}\n"
                f"• Name Servers: {ns_str}\n"
                f"• Status: {w.status or 'N/A'}\n"
            )
            return truncate_or_save(output, max_length=1500, context_name="whois")
    except Exception:
        pass

    # Fallback to RDAP API (HTTP-based WHOIS)
    try:
        res = requests.get(f"https://rdap.org/domain/{clean_domain}", headers=HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", [])}
            ns_list = [ns.get("ldhName") for ns in data.get("nameservers", []) if ns.get("ldhName")]

            output = (
                f"📋 **WHOIS (RDAP) Report for `{clean_domain}`**:\n"
                f"• Domain Name: {data.get('ldhName', clean_domain)}\n"
                f"• Handle: {data.get('handle', 'N/A')}\n"
                f"• Registration Date: {events.get('registration', 'N/A')}\n"
                f"• Expiration Date: {events.get('expiration', 'N/A')}\n"
                f"• Last Changed: {events.get('last changed', 'N/A')}\n"
                f"• Name Servers: {', '.join(ns_list) if ns_list else 'N/A'}\n"
            )
            return output
    except Exception as e:
        return f"Error executing WHOIS/RDAP query for `{clean_domain}`: {e}"

    return f"Unable to fetch WHOIS records for `{clean_domain}`."

@tool
def lookup_subdomains(domain: str) -> str:
    """
    Search Certificate Transparency logs (crt.sh) for subdomains of a given domain.
    """
    clean_domain = domain.strip().replace("http://", "").replace("https://", "").split("/")[0]
    try:
        url = f"https://crt.sh/?q=%.{clean_domain}&output=json"
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return f"❌ CRT.sh API returned HTTP status {res.status_code}"

        data = res.json()
        subdomains = set()
        for item in data:
            name_val = item.get("name_value")
            if name_val:
                for sub in name_val.split("\n"):
                    sub_clean = sub.strip().lower()
                    if not sub_clean.startswith("*.") and clean_domain in sub_clean:
                        subdomains.add(sub_clean)

        sorted_subs = sorted(list(subdomains))
        if not sorted_subs:
            return f"No subdomains found for `{clean_domain}` via Certificate Transparency logs."

        output = (
            f"🔍 **Subdomains Discovered for `{clean_domain}`** (Total: {len(sorted_subs)}):\n\n"
            + "\n".join([f"- `{s}`" for s in sorted_subs[:40]])
        )
        if len(sorted_subs) > 40:
            output += f"\n\n... (Showing top 40 of {len(sorted_subs)} subdomains)"

        return truncate_or_save(output, max_length=2000, context_name="subdomains")
    except Exception as e:
        return f"Error searching subdomains: {e}"

@tool
def search_username_footprint(username: str) -> str:
    """
    Check public account footprint across 20+ social media and developer platforms for a given username.
    """
    clean_user = username.strip().lstrip("@")
    if not clean_user:
        return "Please provide a valid username."

    targets = {
        "GitHub": f"https://github.com/{clean_user}",
        "Twitter/X": f"https://x.com/{clean_user}",
        "Reddit": f"https://www.reddit.com/user/{clean_user}",
        "Telegram": f"https://t.me/{clean_user}",
        "Medium": f"https://medium.com/@{clean_user}",
        "Dev.to": f"https://dev.to/{clean_user}",
        "Pinterest": f"https://www.pinterest.com/{clean_user}/",
        "TikTok": f"https://www.tiktok.com/@{clean_user}",
        "Instagram": f"https://www.instagram.com/{clean_user}/",
        "Steam": f"https://steamcommunity.com/id/{clean_user}",
        "Spotify": f"https://open.spotify.com/user/{clean_user}",
        "GitLab": f"https://gitlab.com/{clean_user}",
        "DockerHub": f"https://hub.docker.com/u/{clean_user}",
        "PyPI": f"https://pypi.org/user/{clean_user}",
        "Linktree": f"https://linktr.ee/{clean_user}",
        "Kaggle": f"https://www.kaggle.com/{clean_user}",
        "HackerNews": f"https://news.ycombinator.com/user?id={clean_user}",
        "SoundCloud": f"https://soundcloud.com/{clean_user}",
        "Hashnode": f"https://hashnode.com/@{clean_user}",
    }

    found = []

    def check_site(name, url):
        try:
            r = requests.head(url, headers=HEADERS, timeout=4, allow_redirects=True)
            if r.status_code == 200:
                return f"✅ [{name}]({url})"
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_site, name, url) for name, url in targets.items()]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                found.append(res)

    if not found:
        return f"No active public profiles found for username `{clean_user}` across checked platforms."

    output = f"👤 **Username Footprint for `{clean_user}`** ({len(found)} active profiles found):\n" + "\n".join(sorted(found))
    return truncate_or_save(output, max_length=1500, context_name="username_osint")

def _convert_to_degrees(value):
    """Helper function to convert GPS coordinates in EXIF to decimal degrees."""
    try:
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return 0.0

@tool
def extract_image_exif(image_source: str) -> str:
    """
    Extract EXIF metadata (camera info, timestamp, software, GPS coordinates) from an image file path or URL.
    """
    src = image_source.strip().strip("'").strip('"')
    is_url = src.startswith("http://") or src.startswith("https://")

    try:
        if is_url:
            r = requests.get(src, headers=HEADERS, timeout=15, stream=True)
            r.raise_for_status()
            img = Image.open(r.raw)
        else:
            if not os.path.exists(src):
                return f"Image file not found at path: `{src}`"
            img = Image.open(src)

        exif_data = img._getexif()
        if not exif_data:
            return f"📷 Image ({img.format}, {img.size[0]}x{img.size[1]} px) loaded successfully, but no EXIF metadata was found in this file."

        parsed_exif = {}
        gps_info = {}

        for tag_id, val in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            if tag_name == "GPSInfo":
                for gps_tag_id in val:
                    sub_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[sub_tag] = val[gps_tag_id]
            else:
                if isinstance(val, (str, int, float)):
                    parsed_exif[tag_name] = val

        output_lines = [f"📸 **Image EXIF Metadata Report** ({img.format}, {img.size[0]}x{img.size[1]} px):"]

        # Core metadata fields
        interesting_keys = ["Make", "Model", "DateTime", "DateTimeOriginal", "Software", "ExposureTime", "FNumber", "ISOSpeedRatings"]
        for key in interesting_keys:
            if key in parsed_exif:
                output_lines.append(f"• **{key}**: {parsed_exif[key]}")

        # Process GPS data if present
        if gps_info:
            lat = gps_info.get("GPSLatitude")
            lat_ref = gps_info.get("GPSLatitudeRef")
            lon = gps_info.get("GPSLongitude")
            lon_ref = gps_info.get("GPSLongitudeRef")

            if lat and lon and lat_ref and lon_ref:
                lat_deg = _convert_to_degrees(lat)
                if str(lat_ref).upper() != "N":
                    lat_deg = -lat_deg

                lon_deg = _convert_to_degrees(lon)
                if str(lon_ref).upper() != "E":
                    lon_deg = -lon_deg

                maps_url = f"https://maps.google.com/?q={lat_deg},{lon_deg}"
                output_lines.append("\n📍 **GPS Location Found!**")
                output_lines.append(f"• Latitude: {lat_deg:.6f}")
                output_lines.append(f"• Longitude: {lon_deg:.6f}")
                output_lines.append(f"• Google Maps Link: {maps_url}")

        if len(output_lines) == 1:
            for k, v in list(parsed_exif.items())[:15]:
                output_lines.append(f"• {k}: {v}")

        return "\n".join(output_lines)
    except Exception as e:
        return f"Error extracting EXIF metadata: {e}"

@tool
def check_wayback_snapshots(url: str) -> str:
    """
    Check historical web page snapshots on Internet Archive Wayback Machine for a URL.
    """
    clean_url = url.strip()
    try:
        api_url = f"http://archive.org/wayback/available?url={clean_url}"
        res = requests.get(api_url, headers=HEADERS, timeout=10)
        data = res.json()
        snapshots = data.get("archived_snapshots", {})

        if not snapshots or "closest" not in snapshots:
            return f"No archived snapshot found on Wayback Machine for `{clean_url}`."

        closest = snapshots["closest"]
        timestamp = closest.get("timestamp", "N/A")
        archive_url = closest.get("url")

        if len(timestamp) == 14:
            formatted_time = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} {timestamp[8:10]}:{timestamp[10:12]}:{timestamp[12:14]}"
        else:
            formatted_time = timestamp

        return (
            f"🏛️ **Wayback Machine Snapshot Found**:\n"
            f"• Target URL: `{clean_url}`\n"
            f"• Closest Snapshot Date: {formatted_time} UTC\n"
            f"• Archived Snapshot Link: {archive_url}\n"
        )
    except Exception as e:
        return f"Error checking Wayback Machine snapshot: {e}"

@tool
def check_email_breach(email: str) -> str:
    """
    Check if an email address has been compromised in known data breaches using XposedOrNot Breach Analytics API.
    Returns the total number of breaches, exposed pastes, compromised data types, and incident details.
    """
    clean_email = email.strip().lower()
    if "@" not in clean_email or "." not in clean_email:
        return f"Invalid email address provided: `{email}`. Please provide a valid email format (e.g. user@example.com)."

    try:
        api_url = f"https://api.xposedornot.com/v1/breach-analytics?email={clean_email}"
        res = requests.get(api_url, headers=HEADERS, timeout=12)

        if res.status_code == 404:
            return f"✅ **Aman!** Email `{clean_email}` tidak ditemukan di basis data kebocoran data (0 breach ditemukan)."

        if res.status_code != 200:
            return f"❌ XposedOrNot API returned status code {res.status_code}: {res.text[:150]}"

        data = res.json()
        exposed_breaches = data.get("ExposedBreaches")
        breaches_details = exposed_breaches.get("breaches_details", []) if exposed_breaches else []

        if not breaches_details:
            return f"✅ **Aman!** Email `{clean_email}` tidak ditemukan di basis data kebocoran data (0 breach)."

        total_breaches = len(breaches_details)
        pastes_cnt = data.get("PastesSummary", {}).get("cnt", 0)

        lines = [
            f"⚠️ **DATA BREACH ALERT**: `{clean_email}`",
            f"• **Total Kebocoran**: {total_breaches} insiden",
            f"• **Exposed Pastes (Pastebin, dsb)**: {pastes_cnt}",
            "",
            "📋 **Daftar Insiden Kebocoran Teratas**:"
        ]

        # Tampilkan hingga 8 insiden pertama
        for i, b in enumerate(breaches_details[:8], 1):
            name = b.get("breach", "Unknown")
            year = b.get("xposed_date", "N/A")
            exposed_data = b.get("xposed_data", "N/A").replace(";", ", ")
            domain = b.get("domain", "")
            pwd_risk = b.get("password_risk", "unknown")

            pwd_flag = " 🔴 (Password Terlibat)" if "password" in pwd_risk.lower() or "password" in exposed_data.lower() else ""
            domain_str = f" ({domain})" if domain else ""

            lines.append(f"{i}. **{name}**{domain_str} - Tahun {year}{pwd_flag}")
            lines.append(f"   • Data Bocor: {exposed_data}")

        if total_breaches > 8:
            lines.append(f"\n... dan {total_breaches - 8} insiden kebocoran lainnya.")

        output = "\n".join(lines)
        return truncate_or_save(output, max_length=2000, context_name="email_breach")
    except Exception as e:
        return f"Error checking email breach status: {e}"

