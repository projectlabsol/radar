import base64
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from pathlib import Path


# =========================================================
# CHARLIE LAUNCHPAD INTELLIGENCE SCANNER
# =========================================================

DB_FILE = Path("launchpad-intel.json")
STATE_FILE = Path("launchpad-scanner-state.json")

NOW = datetime.now(timezone.utc)
TODAY = NOW.date().isoformat()

USER_AGENT = "ProjectLabSol-Launchpad-Radar/1.0"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


LAUNCH_WORDS = [
    "launchpad",
    "memecoin launch",
    "meme coin launch",
    "token launch platform",
    "bonding curve",
    "fair launch",
    "token launcher",
    "coin launcher"
]


GENERIC_NAMES = {
    "new",
    "crypto",
    "token",
    "tokens",
    "meme",
    "memecoin",
    "memecoins",
    "platform",
    "launchpad",
    "launcher",
    "fair",
    "launch",
    "bonding",
    "curve",
    "defi",
    "web3",
    "solana",
    "ethereum",
    "base",
    "bnb",
    "chain",
    "ecosystem",
    "project",
    "protocol"
}


# =========================================================
# BASIC HELPERS
# =========================================================

def log(message):
    print("[RADAR]", message)


def request_headers(url):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*"
    }

    if "api.github.com" in url and GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        headers["Accept"] = "application/vnd.github+json"

    return headers


def fetch_text(url, timeout=20):
    req = urllib.request.Request(
        url,
        headers=request_headers(url)
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def fetch_json(url, timeout=20):
    return json.loads(fetch_text(url, timeout))


def safe_text(url, timeout=15):
    try:
        return fetch_text(url, timeout)
    except Exception as error:
        log(f"Could not read {url}: {error}")
        return ""


def safe_json(url, timeout=20):
    try:
        return fetch_json(url, timeout)
    except Exception as error:
        log(f"Could not read {url}: {error}")
        return None


def load_json(path, default):
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return default


def save_json(path, data):
    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ) + "\n",
        encoding="utf-8"
    )


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "")
    ).strip()


def normalize_name(name):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        clean(name).lower()
    )


def get_domain(url):
    try:
        host = urllib.parse.urlparse(url).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        return host
    except Exception:
        return ""


def name_from_domain(url):
    domain = get_domain(url)

    if not domain:
        return ""

    first = domain.split(".")[0]

    if first in {
        "www",
        "app",
        "docs",
        "blog",
        "go"
    }:
        return ""

    return first.replace("-", " ").title()


# =========================================================
# RELEVANCE / STATUS
# =========================================================

def is_launchpad_signal(text):
    text = clean(text).lower()

    if not any(word in text for word in LAUNCH_WORDS):
        return False

    crypto_words = [
        "meme",
        "token",
        "coin",
        "crypto",
        "web3",
        "solana",
        "ethereum",
        "base",
        "bnb",
        "blockchain",
        "defi"
    ]

    return any(
        word in text
        for word in crypto_words
    )


def classify_status(text, published=None):
    text = clean(text).lower()

    if "testnet" in text:
        return "TESTNET"

    if any(word in text for word in [
        "coming soon",
        "launching soon",
        "pre-launch",
        "prelaunch"
    ]):
        return "COMING SOON"

    if any(word in text for word in [
        "announces",
        "announced",
        "unveils",
        "reveals",
        "introduces",
        "waitlist",
        "early access"
    ]):
        return "ANNOUNCED"

    if any(word in text for word in [
        "now live",
        "is live",
        "launches",
        "launched",
        "goes live",
        "debuted"
    ]):
        if published:
            age = NOW - published

            if age <= timedelta(hours=72):
                return "NEW"

        return "LIVE"

    return "RUMOR"


# =========================================================
# DATE
# =========================================================

def parse_date(value):
    if not value:
        return None

    value = clean(value)

    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d"
    ]

    for fmt in formats:
        try:
            result = datetime.strptime(
                value,
                fmt
            )

            if result.tzinfo is None:
                result = result.replace(
                    tzinfo=timezone.utc
                )

            return result.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    return None


# =========================================================
# X / DISCORD / GITHUB DETECTOR
# =========================================================

def find_public_links(text):
    result = {
        "website": "",
        "x": "",
        "discord": "",
        "github": ""
    }

    if not text:
        return result

    urls = re.findall(
        r"https?://[^\s<>'\"\)\]]+",
        text,
        flags=re.I
    )

    for raw_url in urls:
        url = raw_url.rstrip(
            ".,;:"
        )

        low = url.lower()

        if (
            "x.com/" in low
            or "twitter.com/" in low
        ):
            if not result["x"]:
                if "/intent/" not in low:
                    result["x"] = url

        elif (
            "discord.gg/" in low
            or "discord.com/invite/" in low
        ):
            if not result["discord"]:
                result["discord"] = url

        elif "github.com/" in low:
            if not result["github"]:
                result["github"] = url

        elif not any(domain in low for domain in [
            "t.me/",
            "telegram.me/",
            "dexscreener.com/",
            "news.google.com/"
        ]):
            if not result["website"]:
                result["website"] = url

    return result


def inspect_website(website, extra_text=""):
    content = extra_text or ""

    if website and website.startswith(
        ("http://", "https://")
    ):
        html = safe_text(
            website,
            timeout=12
        )

        content += "\n" + html[:600000]

    links = find_public_links(
        content
    )

    if website and not links["website"]:
        links["website"] = website

    return links


# =========================================================
# NEWS NAME DETECTOR
# =========================================================

def guess_project_name(title):
    title = clean(title)

    # Detect names like Pools.trade
    domain_match = re.search(
        r"\b([a-z0-9][a-z0-9-]{1,30}\."
        r"(?:trade|fun|xyz|io|app|finance|fi|com))\b",
        title,
        flags=re.I
    )

    if domain_match:
        return domain_match.group(1)

    patterns = [
        (
            r"\b([A-Z][A-Za-z0-9._-]{2,30})\s+"
            r"(?:memecoin\s+|meme\s+coin\s+|token\s+)?"
            r"launchpad\b"
        ),
        (
            r"\b([A-Z][A-Za-z0-9._-]{2,30})\s+"
            r"(?:fair[- ]launch|bonding[- ]curve)\b"
        ),
        (
            r"\b(?:launches|unveils|introduces|reveals|announces)\s+"
            r"(?:its\s+)?(?:new\s+)?"
            r"([A-Z][A-Za-z0-9._-]{2,30})\b"
        )
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            title
        )

        if match:
            candidate = match.group(1)

            if candidate.lower() not in GENERIC_NAMES:
                return candidate

    return ""


# =========================================================
# CANDIDATE DATABASE
# =========================================================

def candidate_key(item):
    website = item.get(
        "website",
        ""
    )

    domain = get_domain(
        website
    )

    if domain:
        return domain

    return normalize_name(
        item.get(
            "name",
            ""
        )
    )


def merge_candidate(pool, candidate):
    if not candidate.get("name"):
        return

    key = candidate_key(
        candidate
    )

    if not key:
        return

    if key not in pool:
        pool[key] = candidate
        return

    current = pool[key]

    sources = list(
        dict.fromkeys(
            current.get("_sources", [])
            + candidate.get("_sources", [])
        )
    )

    current["_sources"] = sources

    status_priority = {
        "RUMOR": 0,
        "ANNOUNCED": 1,
        "TESTNET": 2,
        "COMING SOON": 3,
        "NEW": 4,
        "LIVE": 5
    }

    current_status = current.get(
        "status",
        "RUMOR"
    )

    new_status = candidate.get(
        "status",
        "RUMOR"
    )

    if (
        status_priority.get(new_status, 0)
        >
        status_priority.get(current_status, 0)
    ):
        current["status"] = new_status

    fields = [
        "chain",
        "description",
        "website",
        "x",
        "discord",
        "github",
        "source"
    ]

    for field in fields:
        if (
            not current.get(field)
            and candidate.get(field)
        ):
            current[field] = candidate[field]


def load_existing_database():
    db = load_json(
        DB_FILE,
        {
            "updatedAt": TODAY,
            "launchpads": []
        }
    )

    pool = {}

    for item in db.get(
        "launchpads",
        []
    ):
        clone = dict(item)

        clone["_sources"] = [
            source.strip()
            for source in clean(
                item.get(
                    "detectedBy",
                    "Manual"
                )
            ).split("+")
            if source.strip()
        ]

        merge_candidate(
            pool,
            clone
        )

    return db, pool


# =========================================================
# GOOGLE NEWS EARLY SIGNAL
# =========================================================

def scan_news(pool, state):
    log("Scanning public news...")

    queries = [
        '"memecoin launchpad" when:3d',
        '"token launchpad" crypto when:3d',
        '"bonding curve" memecoin platform when:3d',
        '"fair launch" crypto platform when:3d',
        '"launch platform" memecoin when:3d'
    ]

    old_seen = set(
        state.get(
            "news_seen",
            []
        )
    )

    new_seen = set(
        old_seen
    )

    for query in queries:

        params = urllib.parse.urlencode({
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en"
        })

        url = (
            "https://news.google.com/"
            "rss/search?"
            + params
        )

        xml = safe_text(
            url,
            timeout=20
        )

        if not xml:
            continue

        try:
            root = ET.fromstring(xml)
        except Exception:
            continue

        for article in root.findall(
            ".//item"
        )[:30]:

            title = clean(
                article.findtext(
                    "title"
                )
            )

            link = clean(
                article.findtext(
                    "link"
                )
            )

            published = parse_date(
                article.findtext(
                    "pubDate"
                )
            )

            identity = link or title

            if not identity:
                continue

            new_seen.add(
                identity
            )

            if identity in old_seen:
                continue

            if published:
                if NOW - published > timedelta(days=4):
                    continue

            if not is_launchpad_signal(
                title
            ):
                continue

            name = guess_project_name(
                title
            )

            # Avoid inventing a project name.
            if not name:
                continue

            website = ""

            if (
                "." in name
                and " " not in name
            ):
                website = (
                    "https://"
                    + name.lower()
                )

            links = inspect_website(
                website
            ) if website else {
                "website": "",
                "x": "",
                "discord": "",
                "github": ""
            }

            candidate = {
                "name": name,
                "status": classify_status(
                    title,
                    published
                ),
                "chain": "",
                "firstSeen": (
                    published.date().isoformat()
                    if published
                    else TODAY
                ),
                "confidence": 0,
                "detectedBy": "",
                "description": title[:320],
                "website": links.get(
                    "website",
                    website
                ),
                "x": links.get(
                    "x",
                    ""
                ),
                "discord": links.get(
                    "discord",
                    ""
                ),
                "github": links.get(
                    "github",
                    ""
                ),
                "source": link,
                "_sources": [
                    "News"
                ]
            }

            merge_candidate(
                pool,
                candidate
            )

    state["news_seen"] = list(
        new_seen
    )[-1200:]


# =========================================================
# GITHUB EARLY PROJECT DETECTOR
# =========================================================

def github_request(url):
    return safe_json(
        url,
        timeout=25
    )


def scan_github(pool, state):
    log("Scanning GitHub...")

    since = (
        NOW
        - timedelta(days=4)
    ).date().isoformat()

    queries = [
        f"memecoin launchpad in:name,description,readme pushed:>={since}",
        f"token launchpad in:name,description,readme pushed:>={since}",
        f"bonding curve memecoin in:name,description,readme pushed:>={since}",
        f"fair launch token platform in:name,description,readme pushed:>={since}"
    ]

    seen = set(
        state.get(
            "github_seen",
            []
        )
    )

    updated_seen = set(
        seen
    )

    for query in queries:

        url = (
            "https://api.github.com/"
            "search/repositories?"
            + urllib.parse.urlencode({
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": 10
            })
        )

        data = github_request(
            url
        )

        if not isinstance(
            data,
            dict
        ):
            continue

        for repo in data.get(
            "items",
            []
        ):

            full_name = clean(
                repo.get(
                    "full_name"
                )
            )

            if not full_name:
                continue

            updated_seen.add(
                full_name
            )

            name = clean(
                repo.get(
                    "name"
                )
            )

            description = clean(
                repo.get(
                    "description"
                )
            )

            homepage = clean(
                repo.get(
                    "homepage"
                )
            )

            github_url = clean(
                repo.get(
                    "html_url"
                )
            )

            initial_text = (
                name
                + " "
                + description
                + " "
                + homepage
            )

            if not is_launchpad_signal(
                initial_text
            ):
                continue

            readme_text = ""

            readme_url = (
                "https://api.github.com/repos/"
                + urllib.parse.quote(
                    full_name,
                    safe="/"
                )
                + "/readme"
            )

            readme = github_request(
                readme_url
            )

            if (
                isinstance(readme, dict)
                and readme.get("content")
            ):
                try:
                    readme_text = (
                        base64.b64decode(
                            readme["content"]
                        )
                        .decode(
                            "utf-8",
                            errors="replace"
                        )
                    )
                except Exception:
                    readme_text = ""

            combined = (
                initial_text
                + "\n"
                + readme_text[:250000]
            )

            if not is_launchpad_signal(
                combined
            ):
                continue

            links = inspect_website(
                homepage,
                combined
            )

            links["github"] = (
                github_url
                or links.get(
                    "github",
                    ""
                )
            )

            created = parse_date(
                repo.get(
                    "created_at"
                )
            )

            candidate = {
                "name": (
                    name
                    .replace("-", " ")
                    .replace("_", " ")
                    .title()
                ),
                "status": classify_status(
                    combined,
                    created
                ),
                "chain": "",
                "firstSeen": (
                    created.date().isoformat()
                    if created
                    else TODAY
                ),
                "confidence": 0,
                "detectedBy": "",
                "description": (
                    description[:320]
                    or
                    "Recent GitHub project matching launchpad signals."
                ),
                "website": links.get(
                    "website",
                    homepage
                ),
                "x": links.get(
                    "x",
                    ""
                ),
                "discord": links.get(
                    "discord",
                    ""
                ),
                "github": github_url,
                "source": github_url,
                "_sources": [
                    "GitHub"
                ]
            }

            merge_candidate(
                pool,
                candidate
            )

    state["github_seen"] = list(
        updated_seen
    )[-1500:]


# =========================================================
# DEFILLAMA DETECTOR
# =========================================================

def scan_defillama(pool, state):
    log("Scanning DefiLlama...")

    data = safe_json(
        "https://api.llama.fi/protocols",
        timeout=35
    )

    if not isinstance(
        data,
        list
    ):
        return

    launchpads = []
    current_ids = set()

    for protocol in data:

        category = clean(
            protocol.get(
                "category"
            )
        ).lower()

        if "launchpad" not in category:
            continue

        protocol_id = str(
            protocol.get("id")
            or protocol.get("slug")
            or normalize_name(
                protocol.get(
                    "name",
                    ""
                )
            )
        )

        if not protocol_id:
            continue

        current_ids.add(
            protocol_id
        )

        launchpads.append(
            (
                protocol_id,
                protocol
            )
        )

    old_seen = set(
        state.get(
            "defillama_seen",
            []
        )
    )

    # IMPORTANT:
    # First run creates a baseline.
    # Existing old launchpads are NOT marked as new.
    if not old_seen:

        state["defillama_seen"] = sorted(
            current_ids
        )

        log(
            "DefiLlama baseline created: "
            + str(len(current_ids))
        )

        return

    for protocol_id, protocol in launchpads:

        if protocol_id in old_seen:
            continue

        name = clean(
            protocol.get(
                "name"
            )
        )

        website = clean(
            protocol.get(
                "url"
            )
        )

        twitter = clean(
            protocol.get(
                "twitter"
            )
        )

        if (
            twitter
            and not twitter.startswith("http")
        ):
            twitter = (
                "https://x.com/"
                + twitter.lstrip("@")
            )

        description = clean(
            protocol.get(
                "description"
            )
        )

        links = inspect_website(
            website,
            description
        )

        if (
            twitter
            and not links.get("x")
        ):
            links["x"] = twitter

        chains = protocol.get(
            "chains"
        ) or []

        if isinstance(
            chains,
            list
        ):
            chain = ", ".join(
                str(x)
                for x in chains[:4]
            )
        else:
            chain = clean(
                chains
            )

        slug = str(
            protocol.get("slug")
            or name
        )

        candidate = {
            "name": name,
            "status": "LIVE",
            "chain": chain,
            "firstSeen": TODAY,
            "confidence": 0,
            "detectedBy": "",
            "description": (
                description[:320]
                or
                "New launchpad indexed by DefiLlama."
            ),
            "website": links.get(
                "website",
                website
            ),
            "x": links.get(
                "x",
                ""
            ),
            "discord": links.get(
                "discord",
                ""
            ),
            "github": links.get(
                "github",
                ""
            ),
            "source": (
                "https://defillama.com/protocol/"
                + urllib.parse.quote(slug)
            ),
            "_sources": [
                "DefiLlama"
            ]
        }

        merge_candidate(
            pool,
            candidate
        )

    state["defillama_seen"] = sorted(
        current_ids
    )


# =========================================================
# DEXSCREENER / ON-CHAIN SIGNAL
# =========================================================

def scan_dexscreener(pool, state):
    log("Scanning DEX Screener...")

    data = safe_json(
        "https://api.dexscreener.com/"
        "token-profiles/latest/v1",
        timeout=25
    )

    if not isinstance(
        data,
        list
    ):
        return

    old_seen = set(
        state.get(
            "dex_profiles_seen",
            []
        )
    )

    current = set()

    for profile in data:

        chain = clean(
            profile.get(
                "chainId"
            )
        )

        token = clean(
            profile.get(
                "tokenAddress"
            )
        )

        if token:
            current.add(
                chain + ":" + token
            )

    # First run is baseline.
    if not old_seen:

        state["dex_profiles_seen"] = sorted(
            current
        )

        log(
            "DEX Screener baseline created: "
            + str(len(current))
        )

        return

    all_seen = set(
        old_seen
    )

    for profile in data:

        chain = clean(
            profile.get(
                "chainId"
            )
        )

        token = clean(
            profile.get(
                "tokenAddress"
            )
        )

        if not token:
            continue

        identity = (
            chain
            + ":"
            + token
        )

        all_seen.add(
            identity
        )

        if identity in old_seen:
            continue

        description = clean(
            profile.get(
                "description"
            )
        )

        link_text = ""

        for link in (
            profile.get("links")
            or []
        ):

            if not isinstance(
                link,
                dict
            ):
                continue

            link_text += (
                "\n"
                + clean(
                    link.get(
                        "label"
                    )
                )
                + " "
                + clean(
                    link.get(
                        "type"
                    )
                )
                + " "
                + clean(
                    link.get(
                        "url"
                    )
                )
            )

        searchable = (
            description
            + "\n"
            + link_text
        )

        if not is_launchpad_signal(
            searchable
        ):
            continue

        links = find_public_links(
            searchable
        )

        website = links.get(
            "website",
            ""
        )

        name = name_from_domain(
            website
        )

        if not name:
            continue

        candidate = {
            "name": name,
            "status": "RUMOR",
            "chain": chain,
            "firstSeen": TODAY,
            "confidence": 0,
            "detectedBy": "",
            "description": (
                description[:320]
                or
                "On-chain profile contains launchpad signals."
            ),
            "website": website,
            "x": links.get(
                "x",
                ""
            ),
            "discord": links.get(
                "discord",
                ""
            ),
            "github": links.get(
                "github",
                ""
            ),
            "source": clean(
                profile.get(
                    "url"
                )
            ),
            "_sources": [
                "DEX Screener"
            ]
        }

        merge_candidate(
            pool,
            candidate
        )

    state["dex_profiles_seen"] = list(
        all_seen
    )[-2000:]


# =========================================================
# CONFIDENCE SYSTEM
# =========================================================

def calculate_confidence(item):
    sources = set(
        item.get(
            "_sources",
            []
        )
    )

    score = 20

    if "News" in sources:
        score += 28

    if "GitHub" in sources:
        score += 22

    if "DefiLlama" in sources:
        score += 35

    if "DEX Screener" in sources:
        score += 25

    if len(sources) > 1:
        score += min(
            20,
            (len(sources) - 1) * 10
        )

    if item.get("website"):
        score += 5

    if item.get("x"):
        score += 6

    if item.get("discord"):
        score += 6

    if item.get("github"):
        score += 5

    if item.get("status") in [
        "ANNOUNCED",
        "COMING SOON",
        "TESTNET"
    ]:
        score += 8

    return min(
        100,
        max(
            1,
            score
        )
    )


# =========================================================
# FINAL OUTPUT
# =========================================================

def finalize(pool):

    results = []

    for item in pool.values():

        sources = list(
            dict.fromkeys(
                item.get(
                    "_sources",
                    []
                )
            )
        )

        if sources:
            item["detectedBy"] = (
                " + ".join(
                    sources
                )
            )

        old_confidence = int(
            item.get(
                "confidence",
                0
            ) or 0
        )

        item["confidence"] = max(
            old_confidence,
            calculate_confidence(
                item
            )
        )

        item.pop(
            "_sources",
            None
        )

        results.append(
            item
        )

    priority = {
        "COMING SOON": 0,
        "TESTNET": 1,
        "ANNOUNCED": 2,
        "NEW": 3,
        "RUMOR": 4,
        "LIVE": 5
    }

    results.sort(
        key=lambda item: (
            priority.get(
                item.get(
                    "status",
                    "RUMOR"
                ),
                9
            ),
            -int(
                item.get(
                    "confidence",
                    0
                )
            ),
            item.get(
                "name",
                ""
            ).lower()
        )
    )

    return results


# =========================================================
# RUN SCANNER
# =========================================================

def main():

    log(
        "Starting Early Launchpad Intelligence..."
    )

    db, pool = load_existing_database()

    state = load_json(
        STATE_FILE,
        {}
    )

    # Independent sources.
    # One failing source does not stop the others.
    try:
        scan_news(
            pool,
            state
        )
    except Exception as error:
        log(
            "News error: "
            + str(error)
        )

    try:
        scan_github(
            pool,
            state
        )
    except Exception as error:
        log(
            "GitHub error: "
            + str(error)
        )

    try:
        scan_defillama(
            pool,
            state
        )
    except Exception as error:
        log(
            "DefiLlama error: "
            + str(error)
        )

    try:
        scan_dexscreener(
            pool,
            state
        )
    except Exception as error:
        log(
            "DEX Screener error: "
            + str(error)
        )

    launchpads = finalize(
        pool
    )

    db["updatedAt"] = (
        NOW.isoformat(
            timespec="seconds"
        )
        .replace(
            "+00:00",
            "Z"
        )
    )

    db["launchpads"] = launchpads

    state["last_run"] = (
        db["updatedAt"]
    )

    save_json(
        DB_FILE,
        db
    )

    save_json(
        STATE_FILE,
        state
    )

    log(
        "Finished. "
        + str(len(launchpads))
        + " launchpad records."
    )


if __name__ == "__main__":
    main()
