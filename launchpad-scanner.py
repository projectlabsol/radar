import base64
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from pathlib import Path


DB_FILE = Path("launchpad-intel.json")
STATE_FILE = Path("launchpad-scanner-state.json")

SCANNER_VERSION = 3
NOW = datetime.now(timezone.utc)
TODAY = NOW.date().isoformat()

USER_AGENT = "ProjectLabSol-Launchpad-Radar/3.0"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


# =========================================================
# SEARCH TERMS
# =========================================================

LAUNCH_TERMS = (
    "launchpad",
    "token launch platform",
    "memecoin launch",
    "meme coin launch",
    "fair launch",
    "bonding curve",
    "token launcher",
    "coin launcher",
)

CRYPTO_TERMS = (
    "token",
    "coin",
    "memecoin",
    "meme coin",
    "crypto",
    "blockchain",
    "solana",
    "ethereum",
    "base",
    "bnb",
    "defi",
    "onchain",
    "on-chain",
)

PRELAUNCH_TERMS = (
    "coming soon",
    "launching soon",
    "pre-launch",
    "prelaunch",
    "waitlist",
    "testnet",
    "beta",
    "early access",
    "will launch",
    "plans to launch",
)

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
    "protocol",
    "community",
    "official",
    "cryptocurrency",
}


# =========================================================
# KNOWN / OLD LAUNCHPADS
# These must never be reported as new discoveries.
# =========================================================

KNOWN_LAUNCHPADS = {
    "pumpfun",
    "pumpswap",
    "raydium",
    "fourmeme",
    "poolstrade",
    "pools",
    "bonkfun",
    "letsbonk",
    "moonshot",
    "moonit",
    "believe",
    "believeapp",
    "bags",
    "bagsfm",
    "boop",
    "boopfun",
    "clanker",
    "flaunch",
    "daosfun",
    "grafun",
    "virtuals",
    "virtualsprotocol",
    "sunpump",
    "launchlab",
    "pinksale",
    "dxsale",
    "gempad",
    "fjordfoundry",
    "seedify",
    "polkastarter",
}

KNOWN_DOMAINS = {
    "pump.fun",
    "pumpswap.io",
    "raydium.io",
    "four.meme",
    "pools.trade",
    "letsbonk.fun",
    "moonshot.money",
    "moon.it",
    "believe.app",
    "bags.fm",
    "boop.fun",
    "clanker.world",
    "flaunch.gg",
    "dao.fun",
    "gra.fun",
    "virtuals.io",
    "sunpump.meme",
}


# =========================================================
# NEWS / NON-PROJECT DOMAINS
# =========================================================

MEDIA_DOMAINS = {
    "hokanews.com",
    "cryptobriefing.com",
    "coindesk.com",
    "cointelegraph.com",
    "decrypt.co",
    "theblock.co",
    "blockworks.co",
    "beincrypto.com",
    "news.google.com",
    "finance.yahoo.com",
    "yahoo.com",
    "forbes.com",
    "reuters.com",
    "bloomberg.com",
    "cryptonews.com",
    "bitcoin.com",
}

NON_PROJECT_HOSTS = {
    "github.com",
    "gitlab.com",
    "medium.com",
    "substack.com",
    "mirror.xyz",
    "notion.site",
    "notion.so",
    "docs.google.com",
    "drive.google.com",
    "x.com",
    "twitter.com",
    "discord.com",
    "discord.gg",
    "t.me",
    "telegram.me",
    "youtube.com",
    "youtu.be",
    "linktr.ee",
    "linktree.com",
}

BAD_PATH_WORDS = (
    "/blog/",
    "/blogs/",
    "/article/",
    "/articles/",
    "/post/",
    "/posts/",
    "/news/",
    "/tutorial/",
    "/tutorials/",
    "/course/",
    "/courses/",
    "/docs/",
    "/documentation/",
    "/2020/",
    "/2021/",
    "/2022/",
    "/2023/",
    "/2024/",
    "/2025/",
)


# =========================================================
# BASIC HELPERS
# =========================================================

def log(message):
    print("[RADAR]", message)


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def norm(value):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        clean(value).lower()
    )


def host_of(url):
    try:
        host = (
            urllib.parse
            .urlparse(clean(url))
            .netloc
            .lower()
            .split("@")[-1]
            .split(":")[0]
        )

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:
        return ""


def domain_matches(host, domains):
    return any(
        host == domain
        or host.endswith("." + domain)
        for domain in domains
    )


def is_media_url(url):
    host = host_of(url)

    return bool(
        host
        and domain_matches(
            host,
            MEDIA_DOMAINS
        )
    )


def is_known_launchpad(name="", website=""):
    name_key = norm(name)
    host = host_of(website)

    if name_key in KNOWN_LAUNCHPADS:
        return True

    if (
        host
        and domain_matches(
            host,
            KNOWN_DOMAINS
        )
    ):
        return True

    return False


def is_project_homepage(url):
    url = clean(url)

    if not url.startswith(
        ("http://", "https://")
    ):
        return False

    host = host_of(url)

    if not host:
        return False

    if domain_matches(
        host,
        MEDIA_DOMAINS | NON_PROJECT_HOSTS
    ):
        return False

    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "/").lower()

    if any(
        word in path
        for word in BAD_PATH_WORDS
    ):
        return False

    segments = [
        segment
        for segment in path.split("/")
        if segment
    ]

    return len(segments) <= 2


# =========================================================
# HTTP
# =========================================================

def request_headers(url):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }

    if "api.github.com" in url:
        headers["Accept"] = (
            "application/vnd.github+json"
        )

        headers["X-GitHub-Api-Version"] = (
            "2022-11-28"
        )

        if GITHUB_TOKEN:
            headers["Authorization"] = (
                f"Bearer {GITHUB_TOKEN}"
            )

    return headers


def fetch_text(url, timeout=20):
    request = urllib.request.Request(
        url,
        headers=request_headers(url)
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def safe_text(url, timeout=20):
    try:
        return fetch_text(
            url,
            timeout
        )

    except Exception as error:
        log(
            f"Could not read {url}: {error}"
        )
        return ""


def safe_json(url, timeout=25):
    try:
        return json.loads(
            fetch_text(
                url,
                timeout
            )
        )

    except Exception as error:
        log(
            f"Could not read JSON {url}: {error}"
        )
        return None


# =========================================================
# JSON FILES
# =========================================================

def load_json(path, default):
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
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


# =========================================================
# DATES
# =========================================================

def parse_date(value):
    value = clean(value)

    if not value:
        return None

    formats = (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    )

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

    try:
        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00"
            )
        ).astimezone(
            timezone.utc
        )

    except Exception:
        return None


# =========================================================
# SIGNAL DETECTION
# =========================================================

def has_launch_signal(text):
    low = clean(text).lower()

    launch_found = any(
        term in low
        for term in LAUNCH_TERMS
    )

    crypto_found = any(
        term in low
        for term in CRYPTO_TERMS
    )

    return (
        launch_found
        and crypto_found
    )


def has_prelaunch_signal(text):
    low = clean(text).lower()

    return any(
        term in low
        for term in PRELAUNCH_TERMS
    )


def detect_chain(text):
    low = clean(text).lower()
    padded = " " + low + " "

    patterns = (
        (
            "Robinhood Chain",
            ("robinhood chain",)
        ),
        (
            "Solana",
            ("solana",)
        ),
        (
            "Base",
            (
                "base chain",
                "base network",
                " on base "
            )
        ),
        (
            "BNB Chain",
            (
                "bnb chain",
                "binance smart chain",
                " bsc "
            )
        ),
        (
            "Ethereum",
            (
                "ethereum",
                "erc-20",
                "erc20"
            )
        ),
        (
            "Arbitrum",
            ("arbitrum",)
        ),
        (
            "Polygon",
            ("polygon",)
        ),
        (
            "Avalanche",
            ("avalanche",)
        ),
        (
            "Optimism",
            ("optimism",)
        ),
    )

    found = []

    for name, terms in patterns:
        if any(
            term in padded
            for term in terms
        ):
            found.append(name)

    return ", ".join(
        found[:3]
    )


# =========================================================
# STATUS
# =========================================================

def status_from_text(
    text,
    published=None
):
    low = clean(text).lower()

    if "testnet" in low:
        return "TESTNET"

    if any(
        value in low
        for value in (
            "coming soon",
            "launching soon",
            "pre-launch",
            "prelaunch"
        )
    ):
        return "COMING SOON"

    if any(
        value in low
        for value in (
            "announces",
            "announced",
            "unveils",
            "reveals",
            "introduces",
            "waitlist",
            "early access",
            "will launch",
            "plans to launch"
        )
    ):
        return "ANNOUNCED"

    if any(
        value in low
        for value in (
            "now live",
            "is live",
            "launches",
            "launched",
            "goes live",
            "debuted"
        )
    ):
        if (
            published
            and NOW - published
            <= timedelta(hours=72)
        ):
            return "NEW"

        return "LIVE"

    return "RUMOR"


# =========================================================
# PUBLIC LINKS
# =========================================================

def public_links(text):
    result = {
        "website": "",
        "x": "",
        "discord": "",
        "github": ""
    }

    urls = re.findall(
        r"https?://[^\s<>'\"\)\]\}]+",
        text or "",
        flags=re.I
    )

    for raw in urls:
        url = raw.rstrip(
            ".,;:"
        )

        host = host_of(url)
        low = url.lower()

        if not host:
            continue

        # X / TWITTER
        if host in {
            "x.com",
            "twitter.com"
        }:
            if (
                not result["x"]
                and "/intent/" not in low
                and "/share" not in low
            ):
                result["x"] = re.sub(
                    r"^https?://(?:www\.)?twitter\.com/",
                    "https://x.com/",
                    url,
                    flags=re.I
                )

            continue

        # DISCORD
        if (
            host == "discord.gg"
            or (
                host == "discord.com"
                and "/invite/" in low
            )
        ):
            if not result["discord"]:
                result["discord"] = url

            continue

        # GITHUB
        if host == "github.com":
            if not result["github"]:
                result["github"] = url

            continue

        # WEBSITE
        if (
            is_project_homepage(url)
            and not result["website"]
        ):
            result["website"] = url

    return result


# =========================================================
# VERIFY OFFICIAL WEBSITE
# =========================================================

def inspect_official_site(website):
    result = {
        "reachable": False,
        "launch_signal": False,
        "prelaunch_signal": False,
        "chain": "",
        "x": "",
        "discord": "",
        "github": "",
        "text": "",
    }

    if not is_project_homepage(
        website
    ):
        return result

    html = safe_text(
        website,
        15
    )

    if not html:
        return result

    result["reachable"] = True

    visible_text = clean(
        re.sub(
            r"<[^>]+>",
            " ",
            html[:800000]
        )
    )[:30000]

    result["text"] = visible_text

    combined = (
        html[:800000]
        + "\n"
        + visible_text
    )

    result["launch_signal"] = (
        has_launch_signal(
            combined
        )
    )

    result["prelaunch_signal"] = (
        has_prelaunch_signal(
            combined
        )
    )

    result["chain"] = (
        detect_chain(
            combined
        )
    )

    links = public_links(
        combined
    )

    result["x"] = links["x"]
    result["discord"] = links["discord"]
    result["github"] = links["github"]

    return result


# =========================================================
# NEWS HELPERS
# =========================================================

def strip_news_publisher(title):
    return re.sub(
        r"\s+-\s+[^-]{2,100}$",
        "",
        clean(title)
    ).strip()


def guess_name_from_title(title):
    title = strip_news_publisher(
        title
    )

    domain_match = re.search(
        (
            r"\b("
            r"[a-z0-9]"
            r"[a-z0-9-]{1,35}"
            r"\."
            r"(?:trade|fun|xyz|io|app|finance|fi|com|zone|gg)"
            r")\b"
        ),
        title,
        flags=re.I
    )

    if domain_match:
        candidate = domain_match.group(
            1
        )

        if not is_media_url(
            "https://" + candidate
        ):
            return candidate

    patterns = (
        (
            r"\b"
            r"([A-Z][A-Za-z0-9._-]{2,40})"
            r"\s+"
            r"(?:memecoin\s+|meme\s+coin\s+|token\s+)?"
            r"launchpad\b"
        ),
        (
            r"\b"
            r"(?:launches|unveils|introduces|reveals|announces|debuts)"
            r"\s+"
            r"(?:its\s+|the\s+|a\s+|an\s+|new\s+)*"
            r"([A-Z][A-Za-z0-9._-]{2,40})"
            r"\b"
        ),
    )

    generic = {
        norm(value)
        for value in GENERIC_NAMES
    }

    for pattern in patterns:
        match = re.search(
            pattern,
            title
        )

        if match:
            candidate = clean(
                match.group(1)
            ).strip(
                ".,:-"
            )

            if norm(
                candidate
            ) not in generic:
                return candidate

    return ""


# =========================================================
# NAME FROM WEBSITE
# =========================================================

def name_from_website(url):
    host = host_of(url)

    if not host:
        return ""

    parts = host.split(".")

    if len(parts) < 2:
        return ""

    if parts[-1] in {
        "trade",
        "fun",
        "xyz",
        "fi",
        "app",
        "gg",
        "zone"
    }:
        return (
            f"{parts[-2]}.{parts[-1]}"
        )

    return (
        parts[-2]
        .replace("-", " ")
        .title()
    )


# =========================================================
# CANDIDATE MERGE
# =========================================================

def candidate_key(item):
    return (
        norm(
            item.get(
                "name",
                ""
            )
        )
        or norm(
            host_of(
                item.get(
                    "website",
                    ""
                )
            )
        )
    )


def merge(pool, item):
    key = candidate_key(
        item
    )

    if not key:
        return

    item["_sources"] = list(
        dict.fromkeys(
            item.get(
                "_sources",
                []
            )
        )
    )

    item["_publishers"] = list(
        dict.fromkeys(
            item.get(
                "_publishers",
                []
            )
        )
    )

    if key not in pool:
        pool[key] = item
        return

    current = pool[key]

    current["_sources"] = list(
        dict.fromkeys(
            current.get(
                "_sources",
                []
            )
            + item.get(
                "_sources",
                []
            )
        )
    )

    current["_publishers"] = list(
        dict.fromkeys(
            current.get(
                "_publishers",
                []
            )
            + item.get(
                "_publishers",
                []
            )
        )
    )

    status_rank = {
        "RUMOR": 0,
        "ANNOUNCED": 1,
        "TESTNET": 2,
        "COMING SOON": 3,
        "NEW": 4,
        "LIVE": 5
    }

    new_status = item.get(
        "status",
        "RUMOR"
    )

    old_status = current.get(
        "status",
        "RUMOR"
    )

    if (
        status_rank.get(
            new_status,
            0
        )
        >
        status_rank.get(
            old_status,
            0
        )
    ):
        current["status"] = (
            new_status
        )

    for field in (
        "chain",
        "description",
        "website",
        "x",
        "discord",
        "github",
        "source"
    ):
        if (
            not current.get(field)
            and item.get(field)
        ):
            current[field] = (
                item[field]
            )

    old_seen = clean(
        current.get(
            "firstSeen",
            ""
        )
    )

    new_seen = clean(
        item.get(
            "firstSeen",
            ""
        )
    )

    if (
        new_seen
        and (
            not old_seen
            or new_seen < old_seen
        )
    ):
        current["firstSeen"] = (
            new_seen
        )


# =========================================================
# POOLS.TRADE PINNED RECORD
# =========================================================

def pinned_pools_trade():
    site = inspect_official_site(
        "https://pools.trade/"
    )

    return {
        "name": "Pools.trade",
        "status": "LIVE",
        "chain": "Robinhood Chain",
        "firstSeen": "2026-08-05",
        "confidence": 100,
        "detectedBy": "Known platform",
        "description": (
            "Known live memecoin launchpad "
            "on Robinhood Chain."
        ),
        "website": "https://pools.trade/",
        "x": site["x"],
        "discord": site["discord"],
        "github": site["github"],
        "source": "https://pools.trade/",
        "scannerVersion": SCANNER_VERSION,
        "pinned": True,
        "_sources": [
            "Known platform"
        ],
        "_publishers": [],
    }


# =========================================================
# LOAD VERIFIED V3 HISTORY
# This automatically deletes v1/v2 false positives.
# =========================================================

def load_verified_history():
    database = load_json(
        DB_FILE,
        {
            "launchpads": []
        }
    )

    pool = {}

    # Always preserve Pools.trade
    merge(
        pool,
        pinned_pools_trade()
    )

    for item in database.get(
        "launchpads",
        []
    ):
        if not isinstance(
            item,
            dict
        ):
            continue

        if item.get("pinned"):
            continue

        # V1 / V2 RESULTS ARE REMOVED
        if int(
            item.get(
                "scannerVersion",
                0
            )
            or 0
        ) < SCANNER_VERSION:
            continue

        # Only preserve strong v3 results
        if int(
            item.get(
                "confidence",
                0
            )
            or 0
        ) < 80:
            continue

        if is_known_launchpad(
            item.get(
                "name",
                ""
            ),
            item.get(
                "website",
                ""
            )
        ):
            continue

        first_seen = parse_date(
            item.get(
                "firstSeen",
                ""
            )
        )

        # Old candidates eventually disappear
        if (
            first_seen
            and NOW - first_seen
            > timedelta(days=30)
        ):
            continue

        clone = dict(item)

        clone["_sources"] = [
            value.strip()
            for value in clean(
                item.get(
                    "detectedBy",
                    ""
                )
            ).split("+")
            if value.strip()
        ]

        clone["_publishers"] = []

        merge(
            pool,
            clone
        )

    return pool


# =========================================================
# GOOGLE NEWS
# =========================================================

def scan_news(pool, state):
    log(
        "Scanning Google News..."
    )

    queries = (
        '"memecoin launchpad" when:3d',
        '"token launchpad" crypto when:3d',
        '"new launchpad" memecoin when:3d',
        '"coming soon" "launchpad" crypto when:7d',
        '"testnet" "launchpad" token when:7d',
    )

    grouped = {}

    seen = set(
        state.get(
            "news_seen",
            []
        )
    )

    for query in queries:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en"
            }
        )

        feed_url = (
            "https://news.google.com/"
            "rss/search?"
            + params
        )

        xml = safe_text(
            feed_url,
            20
        )

        if not xml:
            continue

        try:
            root = ET.fromstring(
                xml
            )

        except Exception as error:
            log(
                f"News XML error: {error}"
            )
            continue

        for article in root.findall(
            ".//item"
        )[:40]:

            raw_title = clean(
                article.findtext(
                    "title"
                )
            )

            title = strip_news_publisher(
                raw_title
            )

            link = clean(
                article.findtext(
                    "link"
                )
            )

            publisher = clean(
                article.findtext(
                    "source"
                )
            )

            published = parse_date(
                article.findtext(
                    "pubDate"
                )
            )

            if link:
                seen.add(link)

            if (
                published
                and NOW - published
                > timedelta(days=7)
            ):
                continue

            if not has_launch_signal(
                title
            ):
                continue

            name = guess_name_from_title(
                title
            )

            if not name:
                continue

            if is_known_launchpad(
                name
            ):
                continue

            key = norm(name)

            group = grouped.setdefault(
                key,
                {
                    "name": name,
                    "titles": [],
                    "links": [],
                    "publishers": set(),
                    "dates": [],
                }
            )

            group["titles"].append(
                title
            )

            if link:
                group["links"].append(
                    link
                )

            if publisher:
                group["publishers"].add(
                    publisher
                )

            if published:
                group["dates"].append(
                    published
                )

    # NEWS IS CORROBORATION ONLY.
    # IT CAN NEVER PUBLISH A LAUNCHPAD BY ITSELF.

    for group in grouped.values():

        dates = group["dates"]

        published = (
            min(dates)
            if dates
            else None
        )

        titles = " ".join(
            group["titles"]
        )

        candidate = {
            "name": group["name"],
            "status": status_from_text(
                titles,
                published
            ),
            "chain": detect_chain(
                titles
            ),
            "firstSeen": (
                published.date().isoformat()
                if published
                else TODAY
            ),
            "confidence": 0,
            "description": (
                group["titles"][0][:320]
            ),
            "website": "",
            "x": "",
            "discord": "",
            "github": "",
            "source": (
                group["links"][0]
                if group["links"]
                else ""
            ),
            "_sources": [
                "News"
            ],
            "_publishers": sorted(
                group["publishers"]
            ),
        }

        merge(
            pool,
            candidate
        )

    state["news_seen"] = list(
        seen
    )[-2500:]


# =========================================================
# GITHUB README
# =========================================================

def read_github_readme(full_name):
    url = (
        "https://api.github.com/repos/"
        + urllib.parse.quote(
            full_name,
            safe="/"
        )
        + "/readme"
    )

    data = safe_json(
        url,
        25
    )

    if (
        not isinstance(data, dict)
        or not data.get("content")
    ):
        return ""

    try:
        return base64.b64decode(
            data["content"]
        ).decode(
            "utf-8",
            errors="replace"
        )

    except Exception:
        return ""


# =========================================================
# GITHUB SCANNER
# =========================================================

def scan_github(pool, state):
    log(
        "Scanning GitHub..."
    )

    since = (
        NOW
        - timedelta(days=7)
    ).date().isoformat()

    queries = (
        (
            f'"memecoin launchpad" '
            f'in:name,description,readme '
            f'pushed:>={since}'
        ),
        (
            f'"token launchpad" '
            f'in:name,description,readme '
            f'pushed:>={since}'
        ),
        (
            f'"bonding curve" memecoin '
            f'in:name,description,readme '
            f'pushed:>={since}'
        ),
    )

    seen = set(
        state.get(
            "github_seen",
            []
        )
    )

    for query in queries:

        search_url = (
            "https://api.github.com/"
            "search/repositories?"
            + urllib.parse.urlencode(
                {
                    "q": query,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": 15,
                }
            )
        )

        data = safe_json(
            search_url,
            25
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

            seen.add(
                full_name
            )

            repo_name = clean(
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

            # BLOCK GENERIC / TUTORIAL REPOS
            if any(
                bad in repo_name.lower()
                for bad in (
                    "tutorial",
                    "example",
                    "template",
                    "demo",
                    "course",
                    "homework",
                    "bot",
                    "scraper"
                )
            ):
                continue

            # MUST HAVE A REAL PROJECT HOMEPAGE
            if not is_project_homepage(
                homepage
            ):
                continue

            readme = read_github_readme(
                full_name
            )

            repo_text = (
                repo_name
                + " "
                + description
                + "\n"
                + readme[:250000]
            )

            if not has_launch_signal(
                repo_text
            ):
                continue

            # VERIFY WEBSITE
            site = inspect_official_site(
                homepage
            )

            # STRICT:
            # official website itself must confirm launchpad
            if not site["reachable"]:
                continue

            if not site["launch_signal"]:
                continue

            # Need at least X, Discord or GitHub identity
            if not (
                site["x"]
                or site["discord"]
                or site["github"]
            ):
                continue

            name = name_from_website(
                homepage
            )

            if not name:
                continue

            if is_known_launchpad(
                name,
                homepage
            ):
                continue

            created = parse_date(
                repo.get(
                    "created_at"
                )
            )

            combined = (
                repo_text
                + "\n"
                + site["text"]
            )

            candidate = {
                "name": name,
                "status": status_from_text(
                    combined,
                    created
                ),
                "chain": (
                    site["chain"]
                    or detect_chain(
                        combined
                    )
                ),
                "firstSeen": (
                    created.date().isoformat()
                    if created
                    else TODAY
                ),
                "confidence": 0,
                "description": (
                    description[:320]
                    or (
                        f"{name} official website "
                        "and repository contain launchpad signals."
                    )
                ),
                "website": homepage,
                "x": site["x"],
                "discord": site["discord"],
                "github": (
                    github_url
                    or site["github"]
                ),
                "source": github_url,
                "_sources": [
                    "GitHub",
                    "Website"
                ],
                "_publishers": [],
            }

            merge(
                pool,
                candidate
            )

    state["github_seen"] = list(
        seen
    )[-3000:]


# =========================================================
# DEFILLAMA
# =========================================================

def scan_defillama(pool, state):
    log(
        "Scanning DefiLlama..."
    )

    data = safe_json(
        "https://api.llama.fi/protocols",
        35
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
            or norm(
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

    # First run = baseline
    if not old_seen:
        state["defillama_seen"] = (
            sorted(current_ids)
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

        if not name:
            continue

        if not is_project_homepage(
            website
        ):
            continue

        if is_known_launchpad(
            name,
            website
        ):
            continue

        site = inspect_official_site(
            website
        )

        if not site["reachable"]:
            continue

        twitter = clean(
            protocol.get(
                "twitter"
            )
        )

        x_url = site["x"]

        if (
            twitter
            and not x_url
        ):
            if twitter.startswith(
                "http"
            ):
                x_url = twitter
            else:
                x_url = (
                    "https://x.com/"
                    + twitter.lstrip("@")
                )

        chains = (
            protocol.get(
                "chains"
            )
            or []
        )

        if isinstance(
            chains,
            list
        ):
            chain = ", ".join(
                str(value)
                for value in chains[:4]
            )
        else:
            chain = clean(chains)

        description = clean(
            protocol.get(
                "description"
            )
        )

        slug = str(
            protocol.get("slug")
            or name
        )

        candidate = {
            "name": name,
            "status": "NEW",
            "chain": (
                chain
                or site["chain"]
            ),
            "firstSeen": TODAY,
            "confidence": 0,
            "description": (
                description[:320]
                or (
                    "New launchpad indexed "
                    "by DefiLlama."
                )
            ),
            "website": website,
            "x": x_url,
            "discord": site["discord"],
            "github": site["github"],
            "source": (
                "https://defillama.com/"
                "protocol/"
                + urllib.parse.quote(
                    slug
                )
            ),
            "_sources": [
                "DefiLlama",
                "Website"
            ],
            "_publishers": [],
        }

        merge(
            pool,
            candidate
        )

    state["defillama_seen"] = (
        sorted(current_ids)
    )


# =========================================================
# DEXSCREENER LINKS
# =========================================================

def dex_profile_links(profile):
    text = ""

    for item in (
        profile.get("links")
        or []
    ):
        if isinstance(
            item,
            dict
        ):
            text += (
                "\n"
                + clean(
                    item.get(
                        "url"
                    )
                )
            )

    return public_links(
        text
    )


# =========================================================
# DEXSCREENER SCANNER
# =========================================================

def scan_dexscreener(pool, state):
    log(
        "Scanning DEX Screener..."
    )

    data = safe_json(
        (
            "https://api.dexscreener.com/"
            "token-profiles/latest/v1"
        ),
        25
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
                chain
                + ":"
                + token
            )

    # First run = baseline
    if not old_seen:
        state["dex_profiles_seen"] = (
            sorted(current)
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

        links = dex_profile_links(
            profile
        )

        website = links[
            "website"
        ]

        if not is_project_homepage(
            website
        ):
            continue

        # VERIFY WEBSITE
        site = inspect_official_site(
            website
        )

        # Token profile alone can NEVER
        # create a launchpad alert.
        if not site["reachable"]:
            continue

        if not site["launch_signal"]:
            continue

        if not (
            site["x"]
            or site["discord"]
            or site["github"]
        ):
            continue

        name = name_from_website(
            website
        )

        if not name:
            continue

        if is_known_launchpad(
            name,
            website
        ):
            continue

        description = clean(
            profile.get(
                "description"
            )
        )

        combined = (
            description
            + "\n"
            + site["text"]
        )

        candidate = {
            "name": name,
            "status": status_from_text(
                combined,
                NOW
            ),
            "chain": (
                site["chain"]
                or chain
            ),
            "firstSeen": TODAY,
            "confidence": 0,
            "description": (
                description[:320]
                or (
                    f"{name} detected from a "
                    "new on-chain profile and "
                    "verified against its website."
                )
            ),
            "website": website,
            "x": (
                site["x"]
                or links["x"]
            ),
            "discord": (
                site["discord"]
                or links["discord"]
            ),
            "github": (
                site["github"]
                or links["github"]
            ),
            "source": clean(
                profile.get(
                    "url"
                )
            ),
            "_sources": [
                "DEX Screener",
                "Website"
            ],
            "_publishers": [],
        }

        merge(
            pool,
            candidate
        )

    state["dex_profiles_seen"] = list(
        all_seen
    )[-3500:]


# =========================================================
# CONFIDENCE
# =========================================================

def score_candidate(item):

    if item.get("pinned"):
        return 100

    sources = set(
        item.get(
            "_sources",
            []
        )
    )

    publishers = set(
        item.get(
            "_publishers",
            []
        )
    )

    score = 0

    if "Website" in sources:
        score += 35

    if "GitHub" in sources:
        score += 20

    if "DefiLlama" in sources:
        score += 45

    if "DEX Screener" in sources:
        score += 30

    if "News" in sources:
        score += 10

        score += min(
            15,
            max(
                0,
                len(publishers) - 1
            ) * 5
        )

    if item.get("x"):
        score += 8

    if item.get("discord"):
        score += 8

    if item.get("github"):
        score += 5

    if item.get("website"):
        score += 5

    if item.get("status") in {
        "ANNOUNCED",
        "COMING SOON",
        "TESTNET"
    }:
        score += 7

    return min(
        100,
        score
    )


# =========================================================
# PUBLISH FILTER
# =========================================================

def is_publishable(item):

    if item.get("pinned"):
        return True

    sources = set(
        item.get(
            "_sources",
            []
        )
    )

    score = score_candidate(
        item
    )

    # NEWS ALONE = NEVER
    if sources <= {"News"}:
        return False

    # GITHUB ALONE = NEVER
    if (
        "GitHub" in sources
        and "Website" not in sources
        and "DefiLlama" not in sources
        and "DEX Screener" not in sources
    ):
        return False

    # MUST HAVE STRONG EVIDENCE
    if not (
        {
            "Website",
            "DefiLlama",
            "DEX Screener"
        }
        & sources
    ):
        return False

    return score >= 75


# =========================================================
# FINAL CLEANUP
# =========================================================

def finalize(pool):
    results = []

    for item in pool.values():

        name = clean(
            item.get(
                "name"
            )
        )

        website = clean(
            item.get(
                "website"
            )
        )

        if not name:
            continue

        if is_media_url(
            website
        ):
            continue

        if (
            is_known_launchpad(
                name,
                website
            )
            and not item.get(
                "pinned"
            )
        ):
            continue

        if not is_publishable(
            item
        ):
            continue

        sources = list(
            dict.fromkeys(
                item.get(
                    "_sources",
                    []
                )
            )
        )

        publishers = list(
            dict.fromkeys(
                item.get(
                    "_publishers",
                    []
                )
            )
        )

        labels = []

        for source in sources:

            if (
                source == "News"
                and publishers
            ):
                labels.append(
                    (
                        f"News "
                        f"({len(publishers)} publishers)"
                    )
                )

            else:
                labels.append(
                    source
                )

        item["detectedBy"] = (
            " + ".join(labels)
        )

        item["confidence"] = max(
            int(
                item.get(
                    "confidence",
                    0
                )
                or 0
            ),
            score_candidate(
                item
            )
        )

        item["scannerVersion"] = (
            SCANNER_VERSION
        )

        item["lastConfirmed"] = (
            TODAY
        )

        item.pop(
            "_sources",
            None
        )

        item.pop(
            "_publishers",
            None
        )

        for field in (
            "chain",
            "firstSeen",
            "description",
            "website",
            "x",
            "discord",
            "github",
            "source"
        ):
            item[field] = clean(
                item.get(
                    field,
                    ""
                )
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
        "LIVE": 5,
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
            ).lower(),
        )
    )

    return results


# =========================================================
# MAIN
# =========================================================

def main():

    log(
        "Starting Launchpad Intelligence Scanner v3..."
    )

    # Only v3 verified history survives.
    # V1 and V2 false positives disappear.
    pool = load_verified_history()

    state = load_json(
        STATE_FILE,
        {}
    )

    scanners = (
        (
            "News",
            scan_news
        ),
        (
            "GitHub",
            scan_github
        ),
        (
            "DefiLlama",
            scan_defillama
        ),
        (
            "DEX Screener",
            scan_dexscreener
        ),
    )

    for label, scanner in scanners:

        try:
            scanner(
                pool,
                state
            )

        except Exception as error:
            log(
                f"{label} error: {error}"
            )

    launchpads = finalize(
        pool
    )

    updated = NOW.isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )

    database = {
        "updatedAt": updated,
        "scannerVersion": SCANNER_VERSION,
        "launchpads": launchpads,
    }

    save_json(
        DB_FILE,
        database
    )

    state["last_run"] = (
        updated
    )

    state["scanner_version"] = (
        SCANNER_VERSION
    )

    save_json(
        STATE_FILE,
        state
    )

    log(
        (
            f"Finished. "
            f"{len(launchpads)} verified "
            f"launchpad record(s)."
        )
    )


if __name__ == "__main__":
    main()
