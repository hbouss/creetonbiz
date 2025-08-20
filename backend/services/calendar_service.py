# backend/services/calendar_service.py
import datetime, uuid

def _ics_escape(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
    s = s.replace("\r\n", r"\n").replace("\n", r"\n").replace("\r", r"\n")
    return s

def _to_utc_basic(dt_iso: str | None) -> str:
    if not dt_iso:
        dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    try:
        dt = datetime.datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.datetime.strptime(dt_iso, "%Y-%m-%d")
        except Exception:
            dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")

def ics_from_events(project_title: str, events: list) -> str:
    """
    events: liste de dicts ET/OU d’objets (avec .title/.start_iso/.end_iso).
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CreeTonBiz//ActionPlan//FR",
        f"X-WR-CALNAME:{_ics_escape(project_title)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for ev in (events or []):
        if isinstance(ev, dict):
            title = ev.get("title") or project_title
            desc  = ev.get("description") or ""
            start = ev.get("start_iso")
            end   = ev.get("end_iso")
        else:
            title = getattr(ev, "title", project_title)
            desc  = getattr(ev, "description", "") or ""
            start = getattr(ev, "start_iso", None)
            end   = getattr(ev, "end_iso", None)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4().hex}@creetonbiz",
            f"DTSTAMP:{now}",
            f"DTSTART:{_to_utc_basic(start)}",
            f"DTEND:{_to_utc_basic(end)}",
            f"SUMMARY:{_ics_escape(title)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            "BEGIN:VALARM",
            "TRIGGER:-PT30M",
            "ACTION:DISPLAY",
            "DESCRIPTION:Rappel",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"