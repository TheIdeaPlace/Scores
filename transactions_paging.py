"""Pure: how the Transactions screen walks ESPN's `/transactions`, on both apps.

No PyQt import, so it is tested on any platform. The iPhone's twin is
`Models/TransactionPaging.swift`; both are held to tests/fixtures/transactions_paging_grid.json.
Change both together.

The screen is one running list, newest first, that loads older transactions as you go, and
"Go to Month" starts it at the end of any month back to January 2001 and keeps going older from
there. What ESPN does, checked 2026-11-07 on every league with a feed:

- `season=Y` is the calendar year Y, January to December, in every league, NBA and NHL too.
  With no `season` it is the year so far. Pages run newest first, `pageCount` says how many.
- `dates=YYYYMMDD-YYYYMMDD` narrows it, but a range over about a year is a 400 ("The dates range
  specified is too large"), so a jump asks for January 1 to the month's last day of that year.
- `team=` ignores `dates` altogether and answers the team's whole year, so a team's jump asks
  for its year and leaves out what's newer than the month. A team's year is a few pages at most.
  Its items carry no `team`.
- Soccer answers oldest first and ignores `dates` (always nothing), so a load finishes a soccer
  year before it shows any of it, in pages of 200 (500 is a 500 error from ESPN for the Premier
  League's 2024, 400 isn't), and puts it newest first. A year is up to four pages: the Premier
  League had 611 in 2025. The newest year often has nothing yet. Its items are transfers,
  with an athlete, `from`, `to` and `type` and no description or team, and a team's list is
  `{"in": [...], "out": [...]}` instead of a list.
- College leagues answer every request with nothing.
- An item's date is midnight Pacific in UTC ("2026-11-02T08:00Z"), so its first ten characters
  are the day it was filed. A range's edge can bring in the next day; the month check drops it.
- Some stretches can't be had at all. NFL 2003 from February to early August answers 404
  ("application error") for any page that reaches into it, at any page size, and for any
  `dates` range that touches it. A 400 or 404 is skipped: the list says so and goes on to the
  year before, rather than stopping there for good or failing every time it is asked.

A cursor is where the next request starts: {"year", "month", "page"}. `month` is the month a
jump starts at, and None once the list has gone past that year.
"""

import calendar
import re

EARLIEST_YEAR = 2001
PAGE_SIZE = 50
WHOLE_YEAR_PAGE_SIZE = 200
# One load asks again while it has found nothing to show, but no more than this many times:
# a college league has nothing in any year.
MAX_REQUESTS_PER_LOAD = 6
# And never more requests than this in one load, whatever they found.
MAX_PAGES_PER_LOAD = 30

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def month_label(year, month):
    """'March 2003'."""
    return f"{MONTH_NAMES[month - 1]} {year}"


def months_back(today_year, today_month):
    """Every month that can be jumped to, newest first: this one back to January 2001."""
    months = []
    year, month = today_year, today_month
    while year >= EARLIEST_YEAR:
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


def start_cursor(today_year, today_month, year=None, month=None):
    """Where the list starts: now, or the end of the month jumped to. This month, or a month
    after it, is now. Before 2001 is January 2001."""
    if year is None or month is None or (year, month) >= (today_year, today_month):
        return {"year": today_year, "month": None, "page": 1}
    if year < EARLIEST_YEAR:
        year, month = EARLIEST_YEAR, 1
    return {"year": year, "month": month, "page": 1}


def whole_year_at_once(league_path):
    """Soccer: oldest first and no dates, so a year comes in one request."""
    return league_path.startswith("soccer/")


def _last_day(year, month):
    return calendar.monthrange(year, month)[1]


def request_params(cursor, league_path, team_id=None):
    """The query for a cursor, as text, in the order it is sent."""
    year, month = cursor["year"], cursor["month"]
    whole_year = whole_year_at_once(league_path)
    params = {"limit": str(WHOLE_YEAR_PAGE_SIZE if whole_year else PAGE_SIZE), "page": str(cursor["page"])}
    if month and not team_id and not whole_year:
        params["dates"] = f"{year}0101-{year}{month:02d}{_last_day(year, month):02d}"
    else:
        params["season"] = str(year)
    if team_id:
        params["team"] = str(team_id)
    return params


def keeps(cursor, date_text):
    """Whether an item belongs where the cursor is: in its year, and no later than the month
    jumped to. One with no date that can be read is kept rather than lost."""
    day = date_text[:10] if isinstance(date_text, str) else ""
    if not _DAY.fullmatch(day):
        return True
    year, month = cursor["year"], cursor["month"]
    if int(day[:4]) != year:
        return False
    return not month or day <= f"{year}-{month:02d}-{_last_day(year, month):02d}"


def newest_first(dates):
    """The order to show one answer's items in, as indexes: newest first, ties as ESPN sent
    them, and anything with no readable date last."""
    def key(index):
        day = dates[index][:10] if isinstance(dates[index], str) else ""
        return day if _DAY.fullmatch(day) else ""
    return sorted(range(len(dates)), key=key, reverse=True) if dates else []


def next_cursor(cursor, has_more):
    """Where to go after an answer: its next page, or the year before, or nowhere after 2001."""
    if has_more:
        return {"year": cursor["year"], "month": cursor["month"], "page": cursor["page"] + 1}
    if cursor["year"] - 1 < EARLIEST_YEAR:
        return None
    return {"year": cursor["year"] - 1, "month": None, "page": 1}


def after_no_answer(cursor):
    """Where to go when ESPN has no answer (400 or 404) for a cursor: the year before."""
    return next_cursor(cursor, False)


def counts_against_limit(answered, kept):
    """Whether a request counts toward MAX_REQUESTS_PER_LOAD. A page whose items were all left
    out (a team's jump passing over what's newer than the month) doesn't: stopping there would
    say the month had none when it hadn't been reached. MAX_PAGES_PER_LOAD still caps it."""
    return answered == 0 or kept > 0


def load_continues(found, requests, cursor, following, league_path, pages):
    """Whether one load asks again after an answer: while it has nothing to show, and in soccer
    until the year is finished, so a year never comes out half in order. `requests` is what
    counts against MAX_REQUESTS_PER_LOAD (counts_against_limit) and `pages` every request,
    which never passes MAX_PAGES_PER_LOAD. After a skip (after_no_answer) with something found,
    the year has changed, so it stops, and the skip's notice goes below what was found."""
    if following is None or pages >= MAX_PAGES_PER_LOAD:
        return False
    if found and whole_year_at_once(league_path) and following["year"] == cursor["year"]:
        return True
    return found == 0 and requests < MAX_REQUESTS_PER_LOAD


def transaction_items(listed):
    """The items in an answer's `transactions`: a list, or a soccer team's `in` and `out`."""
    if isinstance(listed, list):
        return [item for item in listed if isinstance(item, dict)]
    if isinstance(listed, dict):
        return [item for side in ("in", "out") if isinstance(listed.get(side), list)
                for item in listed[side] if isinstance(item, dict)]
    return []


def _name(entry):
    entry = entry if isinstance(entry, dict) else {}
    name = entry.get("displayName")
    return name.strip() if isinstance(name, str) else ""


def _grouped(number):
    return f"{number:,}"


def describe(item):
    """What a transaction says: ESPN's description, or for a soccer transfer, who moved where.
    "" if there is nothing to say."""
    description = item.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip()
    athlete, origin, destination = _name(item.get("athlete")), _name(item.get("from")), _name(item.get("to"))
    if not (athlete or origin or destination):
        return ""
    text = athlete or "A player"
    if destination:
        text += f" joins {destination}"
        if origin:
            text += f" from {origin}"
    elif origin:
        text += f" leaves {origin}"
    kind = item.get("type") if isinstance(item.get("type"), str) else ""
    amount = item.get("amount")
    if kind == "Loan":
        text += " on loan"
    elif kind == "Free":
        text += " on a free transfer"
    elif kind == "Undisclosed":
        text += " for an undisclosed fee"
    elif kind == "Swap":
        text += " in a swap"
    elif kind == "Fee" and isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 0:
        currency = item.get("currency") if isinstance(item.get("currency"), dict) else {}
        number = _grouped(int(amount))
        if currency.get("code"):
            text += f" for {number} {currency['code']}"
        elif currency.get("sign"):
            text += f" for {currency['sign']}{number}"
        else:
            text += f" for {number}"
    elif kind == "Fee":
        text += " for a fee"
    return text + "."


def _subject(team_name):
    return f"{team_name} transactions" if team_name else "transactions"


def jump_notice(year, month, dates, team_name=None):
    """Said above the list when the month jumped to has none but older ones were found."""
    if not dates:
        return None
    prefix = f"{year}-{month:02d}"
    if any(isinstance(d, str) and d.startswith(prefix) for d in dates):
        return None
    return f"No {_subject(team_name)} in {month_label(year, month)}. Older ones follow."


def nothing_found(oldest_year, jumped_to=None, team_name=None):
    """Said when a load found nothing at all, back to January of `oldest_year`."""
    subject = _subject(team_name)
    if jumped_to:
        year, month = jumped_to
        if (oldest_year, 1) == (year, month):
            return f"No {subject} in {month_label(year, month)}."
        return f"No {subject} from January {oldest_year} to {month_label(year, month)}."
    return f"No {subject} since January {oldest_year}."


def skipped_text(year, team_name=None):
    """Said where ESPN had no answer for part of a year and the list went on without it."""
    text = f"ESPN couldn't provide some of {year}'s {_subject(team_name)}"
    return text + (f", so the list goes on with {year - 1}." if year > EARLIEST_YEAR else ".")


def nothing_older(oldest_year, team_name=None):
    """Said when loading more found nothing, back to January of `oldest_year`."""
    return f"No older {_subject(team_name)} found back to January {oldest_year}."


def end_text(team_name=None):
    """Said at the bottom when there is nothing older to load."""
    return f"No older {_subject(team_name)}. The list goes back to January {EARLIEST_YEAR}."
