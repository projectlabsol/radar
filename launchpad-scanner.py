import base64
import html as html_lib
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from pathlib import Path


# =========================================================
# LAUNCHPAD INTELLIGENCE RADAR v5
# =========================================================

DB_FILE = Path("launchpad-intel.json")
STATE_FILE = Path("launchpad-scanner-state.json")

SCANNER_VERSION = 5

NOW = datetime.now(timezone.utc)
TODAY = NOW.date().isoformat()

USER_AGENT = "ProjectLabSol-Launchpad-Radar/5.0"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

# =========================================================
# DISCORD COMMUNITY WATCH
# Cryptic Crypto = fuente principal
# =========================================================

DISCORD_WATCH_SOURCES = (
    {
        "name": "Cryptic Crypto",
        "invite": "https://discord.gg/cryptic-crypto",
        "primary": True,
    },
    {
        "name": "Degen Whales",
        "invite": "https://discord.gg/degenwhales",
        "primary": False,
    },
    {
        "name": "",
        "invite": "https://discord.gg/UXWkB5j8C",
        "primary": False,
    },
    {
        "name": "",
        "invite": "https://discord.gg/G3EjhhhbN",
        "primary": False,
    },
    {
        "name": "",
        "invite": "https://discord.gg/kvUd7dFV4",
        "primary": False,
    },
)
# =========================================================
# KNOWN LAUNCHPADS
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
    "clankerworld",
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
# BLOCKED DOMAINS
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

SOCIAL_DOMAINS = {
    "instagram.com",
    "tiktok.com",
    "pinterest.com",
    "facebook.com",
    "threads.net",
    "reddit.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "t.me",
    "telegram.me",
    "x.com",
    "twitter.com",
    "discord.com",
    "discord.gg",
}

GENERIC_HOSTS = {
    "vercel.app",
    "netlify.app",
    "pages.dev",
    "github.io",
    "onrender.com",
    "render.com",
    "railway.app",
    "replit.app",
    "herokuapp.com",
    "web.app",
    "firebaseapp.com",
    "wixsite.com",
    "carrd.co",
    "notion.site",
    "notion.so",
    "medium.com",
    "substack.com",
    "mirror.xyz",
    "linktr.ee",
    "linktree.com",
}

BAD_PATHS = (
    "/blog/",
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
)


# =========================================================
# LAUNCH SIGNALS
# =========================================================

POSITIVE_PATTERNS = (
    r"\blaunchpad\b",
    r"\btoken launcher\b",
    r"\bcoin launcher\b",
    r"\bmemecoin launcher\b",
    r"\bmeme coin launcher\b",
    r"\bfair launch platform\b",
    r"\btoken launch platform\b",
    r"\bmemecoin launch platform\b",
    r"\blaunch your token\b",
    r"\blaunch a token\b",
    r"\blaunch tokens\b",
    r"\blaunch your coin\b",
    r"\blaunch a coin\b",
    r"\bcreate your token\b",
    r"\bcreate a token\b",
    r"\bdeploy your token\b",
    r"\bdeploy a token\b",
    r"\bcreate and launch\b",
    r"\blaunch and trade tokens\b",
)

NEGATIVE_PATTERNS = (
    r"\bnot a bonding curve\b",
    r"\bnot a launchpad\b",
    r"\bnot a token launchpad\b",
    r"\bnot a token launcher\b",
    r"\bnot a launcher\b",
    r"\bno bonding curve\b",
    r"\bno bonding curves\b",
    r"\bwithout a bonding curve\b",
    r"\bwithout bonding curves\b",
    r"\binstead of a bonding curve\b",
    r"\bwe are not a launchpad\b",
    r"\bwe're not a launchpad\b",
)

PRELAUNCH_TERMS = (
    "coming soon",
    "launching soon",
    "launch soon",
    "pre-launch",
    "prelaunch",
    "waitlist",
    "testnet",
    "early access",
    "will launch",
    "plans to launch",
    "beta launch",
)


# =========================================================
# HELPERS
# =========================================================

def log(message):
    print("[RADAR]", message)


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def normalize(value):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        clean(value).lower()
    )


def get_host(url):
    try:
        host = (
            urllib.parse.urlparse(clean(url))
            .netloc.lower()
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
        host == item
        or host.endswith("." + item)
        for item in domains
    )


def is_known_launchpad(name="", website=""):
    if normalize(name) in KNOWN_LAUNCHPADS:
        return True

    host = get_host(website)

    return bool(
        host
        and domain_matches(
            host,
            KNOWN_DOMAINS
        )
    )


def valid_project_domain(url):
    url = clean(url)

    if not url.startswith(
        ("http://", "https://")
    ):
        return False

    host = get_host(url)

    if not host:
        return False

    blocked = (
        MEDIA_DOMAINS
        | SOCIAL_DOMAINS
        | GENERIC_HOSTS
    )

    if domain_matches(
        host,
        blocked
    ):
        return False

    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "/").lower()

    if any(
        value in path
        for value in BAD_PATHS
    ):
        return False

    parts = [
        value
        for value in path.split("/")
        if value
    ]

    return len(parts) <= 2


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
    req = urllib.request.Request(
        url,
        headers=request_headers(url)
    )

    with urllib.request.urlopen(
        req,
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
# FILES
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
# DATE
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

    return None


# =========================================================
# HTML TEXT
# =========================================================

def visible_html_text(raw_html):
    raw_html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        raw_html,
        flags=re.I | re.S
    )

    raw_html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        raw_html,
        flags=re.I | re.S
    )

    raw_html = re.sub(
        r"<svg\b[^>]*>.*?</svg>",
        " ",
        raw_html,
        flags=re.I | re.S
    )

    raw_html = re.sub(
        r"<[^>]+>",
        " ",
        raw_html
    )

    return clean(
        html_lib.unescape(
            raw_html
        )
    )


# =========================================================
# LAUNCH DETECTION
# =========================================================

def remove_negative_phrases(text):
    text = clean(text).lower()

    for pattern in NEGATIVE_PATTERNS:
        text = re.sub(
            pattern,
            " ",
            text,
            flags=re.I
        )

    return clean(text)


def has_launch_signal(text):
    text = remove_negative_phrases(
        text
    )

    return any(
        re.search(
            pattern,
            text,
            flags=re.I
        )
        for pattern in POSITIVE_PATTERNS
    )


def has_prelaunch_signal(text):
    low = clean(text).lower()

    return any(
        value in low
        for value in PRELAUNCH_TERMS
    )


# =========================================================
# CHAIN
# =========================================================

def detect_chain(text):
    low = (
        " "
        + clean(text).lower()
        + " "
    )

    chains = (
        (
            "Robinhood Chain",
            ("robinhood chain",)
        ),
        (
            "Solana",
            ("solana",)
        ),
        (
            "Midnight",
            (
                "midnight network",
                "midnight chain"
            )
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
                " bsc ",
                "binance smart chain"
            )
        ),
        (
            "Ethereum",
            (
                "ethereum",
                "erc20",
                "erc-20"
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
        (
            "Sui",
            (" sui ",)
        ),
        (
            "Aptos",
            ("aptos",)
        ),
        (
            "Monad",
            ("monad",)
        ),
        (
            "Berachain",
            ("berachain",)
        ),
        (
            "Sonic",
            ("sonic chain",)
        ),
        (
            "Sei",
            (" sei ",)
        ),
        (
            "TON",
            (
                " ton ",
                "the open network"
            )
        ),
        (
            "Tron",
            ("tron",)
        ),
        (
            "Abstract",
            ("abstract chain",)
        ),
        (
            "HyperEVM",
            ("hyperevm",)
        ),
    )

    found = []

    for name, aliases in chains:
        if any(
            alias in low
            for alias in aliases
        ):
            found.append(name)

    return ", ".join(
        found[:3]
    )


# =========================================================
# STATUS
# =========================================================

def detect_status(
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
            "launch soon",
            "pre-launch",
            "prelaunch",
        )
    ):
        return "COMING SOON"

    if any(
        value in low
        for value in (
            "announced",
            "announces",
            "unveils",
            "reveals",
            "introduces",
            "waitlist",
            "early access",
            "will launch",
            "plans to launch",
        )
    ):
        return "ANNOUNCED"

    if any(
        value in low
        for value in (
            "now live",
            "is live",
            "launched",
            "launches",
            "goes live",
            "debuted",
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
# LINKS
# =========================================================

def extract_links(text):
    result = {
        "website": "",
        "x": "",
        "discord": "",
        "github": "",
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

        host = get_host(url)
        low = url.lower()

        if not host:
            continue

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

        if host == "github.com":
            if not result["github"]:
                result["github"] = url

            continue

        if (
            valid_project_domain(url)
            and not result["website"]
        ):
            result["website"] = url

    return result


# =========================================================
# WEBSITE
# =========================================================

def inspect_website(website):
    result = {
        "reachable": False,
        "launchSignal": False,
        "prelaunchSignal": False,
        "chain": "",
        "x": "",
        "discord": "",
        "github": "",
        "text": "",
    }

    if not valid_project_domain(
        website
    ):
        return result

    raw_html = safe_text(
        website,
        15
    )

    if not raw_html:
        return result

    result["reachable"] = True

    text = visible_html_text(
        raw_html[:900000]
    )[:40000]

    result["text"] = text

    result["launchSignal"] = (
        has_launch_signal(
            text
        )
    )

    result["prelaunchSignal"] = (
        has_prelaunch_signal(
            text
        )
    )

    result["chain"] = (
        detect_chain(
            text
        )
    )

    links = extract_links(
        raw_html[:900000]
    )

    result["x"] = links["x"]
    result["discord"] = links[
        "discord"
    ]
    result["github"] = links[
        "github"
    ]

    return result


# =========================================================
# PROJECT NAME
# =========================================================

def name_from_website(url):
    host = get_host(url)

    if not host:
        return ""

    parts = host.split(".")

    if len(parts) < 2:
        return ""

    special = {
        "trade",
        "fun",
        "xyz",
        "fi",
        "app",
        "gg",
        "zone",
    }

    if parts[-1] in special:
        return (
            f"{parts[-2]}.{parts[-1]}"
        )

    return (
        parts[-2]
        .replace("-", " ")
        .title()
    )


# =========================================================
# DEFILLAMA
# =========================================================

def build_defillama_registry():
    log(
        "Loading DefiLlama registry..."
    )

    data = safe_json(
        "https://api.llama.fi/protocols",
        35
    )

    registry = {
        "protocols": [],
        "byName": {},
        "byDomain": {},
        "launchpadIds": set(),
    }

    if not isinstance(
        data,
        list
    ):
        return registry

    for protocol in data:
        name = clean(
            protocol.get(
                "name"
            )
        )

        category = clean(
            protocol.get(
                "category"
            )
        )

        website = clean(
            protocol.get(
                "url"
            )
        )

        protocol_id = str(
            protocol.get("id")
            or protocol.get("slug")
            or normalize(name)
        )

        entry = {
            "id": protocol_id,
            "name": name,
            "category": category,
            "website": website,
            "chains": (
                protocol.get(
                    "chains"
                )
                or []
            ),
            "twitter": clean(
                protocol.get(
                    "twitter"
                )
            ),
            "description": clean(
                protocol.get(
                    "description"
                )
            ),
            "slug": str(
                protocol.get(
                    "slug"
                )
                or name
            ),
        }

        registry[
            "protocols"
        ].append(entry)

        name_key = normalize(name)

        if name_key:
            registry[
                "byName"
            ][name_key] = entry

        host = get_host(website)

        if host:
            registry[
                "byDomain"
            ][host] = entry

        if "launchpad" in category.lower():
            registry[
                "launchpadIds"
            ].add(
                protocol_id
            )

    return registry


def find_defillama_protocol(
    name,
    website,
    registry
):
    name_key = normalize(name)

    if name_key in registry[
        "byName"
    ]:
        return registry[
            "byName"
        ][name_key]

    host = get_host(
        website
    )

    if not host:
        return None

    for known_host, protocol in (
        registry[
            "byDomain"
        ].items()
    ):
        if (
            host == known_host
            or host.endswith(
                "." + known_host
            )
            or known_host.endswith(
                "." + host
            )
        ):
            return protocol

    return None


def existing_nonlaunchpad(
    name,
    website,
    registry
):
    protocol = (
        find_defillama_protocol(
            name,
            website,
            registry
        )
    )

    if not protocol:
        return False

    category = (
        protocol["category"]
        .lower()
    )

    return "launchpad" not in category


# =========================================================
# MERGE
# =========================================================

def candidate_tokens(item):
    result = set()

    name = normalize(
        item.get(
            "name",
            ""
        )
    )

    if name:
        result.add(name)

    host = get_host(
        item.get(
            "website",
            ""
        )
    )

    if host:
        result.add(
            normalize(host)
        )

        stem = host.split(".")[0]

        if len(stem) >= 4:
            result.add(
                normalize(stem)
            )

    return result


def merge_candidate(
    pool,
    candidate
):
    tokens = candidate_tokens(
        candidate
    )

    if not tokens:
        return

    found = None

    for key, existing in pool.items():
        if tokens & candidate_tokens(
            existing
        ):
            found = key
            break

    if found is None:
        pool[
            sorted(tokens)[0]
        ] = candidate

        return

    current = pool[found]

    current["_sources"] = list(
        dict.fromkeys(
            current.get(
                "_sources",
                []
            )
            + candidate.get(
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
            + candidate.get(
                "_publishers",
                []
            )
        )
    )

    ranking = {
        "RUMOR": 0,
        "ANNOUNCED": 1,
        "TESTNET": 2,
        "COMING SOON": 3,
        "NEW": 4,
        "LIVE": 5,
    }

    if (
        ranking.get(
            candidate.get(
                "status",
                "RUMOR"
            ),
            0
        )
        >
        ranking.get(
            current.get(
                "status",
                "RUMOR"
            ),
            0
        )
    ):
        current["status"] = (
            candidate["status"]
        )

    for field in (
        "chain",
        "description",
        "website",
        "x",
        "discord",
        "github",
        "source",
    ):
        if (
            not current.get(field)
            and candidate.get(field)
        ):
            current[field] = (
                candidate[field]
            )


# =========================================================
# POOLS.TRADE
# =========================================================

def pools_trade_record():
    site = inspect_website(
        "https://pools.trade/"
    )

    return {
        "name": "Pools.trade",
        "status": "LIVE",
        "radarTier": "KNOWN",
        "chain": "Robinhood Chain",
        "firstSeen": "2026-08-05",
        "confidence": 100,
        "description": (
            "Known live memecoin "
            "launchpad on Robinhood Chain."
        ),
        "website": (
            "https://pools.trade/"
        ),
        "x": site["x"],
        "discord": site[
            "discord"
        ],
        "github": site[
            "github"
        ],
        "source": (
            "https://pools.trade/"
        ),
        "detectedBy": (
            "Known platform"
        ),
        "scannerVersion": (
            SCANNER_VERSION
        ),
        "pinned": True,
        "_sources": [
            "Known platform"
        ],
        "_publishers": [],
    }


# =========================================================
# HISTORY
# v4 and older candidates are removed.
# =========================================================

def load_history():
    pool = {}

    merge_candidate(
        pool,
        pools_trade_record()
    )

    database = load_json(
        DB_FILE,
        {
            "launchpads": []
        }
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

        if item.get(
            "pinned"
        ):
            continue

        if int(
            item.get(
                "scannerVersion",
                0
            )
            or 0
        ) != SCANNER_VERSION:
            continue

        if int(
            item.get(
                "confidence",
                0
            )
            or 0
        ) < 65:
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

        clone[
            "_publishers"
        ] = []

        merge_candidate(
            pool,
            clone
        )

    return pool


# =========================================================
# NEWS
# =========================================================

def strip_publisher(title):
    return re.sub(
        r"\s+-\s+[^-]{2,100}$",
        "",
        clean(title)
    ).strip()


def guess_news_name(title):
    title = strip_publisher(
        title
    )

    domain_match = re.search(
        (
            r"\b("
            r"[a-z0-9][a-z0-9-]{1,35}"
            r"\."
            r"(?:trade|fun|xyz|io|app|fi|gg|zone)"
            r")\b"
        ),
        title,
        flags=re.I
    )

    if domain_match:
        return domain_match.group(
            1
        )

    match = re.search(
        (
            r"\b"
            r"([A-Z][A-Za-z0-9._-]{2,40})"
            r"\s+"
            r"(?:memecoin\s+|token\s+)?"
            r"launchpad\b"
        ),
        title
    )

    if match:
        return match.group(1)

    return ""


def scan_news(
    pool,
    state,
    registry
):
    log(
        "Scanning Google News..."
    )

    queries = (
        '"new memecoin launchpad" when:3d',
        '"new token launchpad" when:3d',
        '"coming soon" "launchpad" crypto when:7d',
        '"launching soon" "launchpad" crypto when:7d',
        '"testnet" "token launchpad" when:7d',
    )

    grouped = {}

    for query in queries:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            }
        )

        xml = safe_text(
            (
                "https://news.google.com/"
                "rss/search?"
                + params
            ),
            20
        )

        if not xml:
            continue

        try:
            root = ET.fromstring(
                xml
            )

        except Exception:
            continue

        for article in root.findall(
            ".//item"
        )[:40]:

            title = strip_publisher(
                article.findtext(
                    "title"
                )
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

            name = guess_news_name(
                title
            )

            if not name:
                continue

            if is_known_launchpad(
                name
            ):
                continue

            key = normalize(name)

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

            group[
                "titles"
            ].append(title)

            if link:
                group[
                    "links"
                ].append(link)

            if publisher:
                group[
                    "publishers"
                ].add(
                    publisher
                )

            if published:
                group[
                    "dates"
                ].append(
                    published
                )

    for group in grouped.values():
        publishers = sorted(
            group[
                "publishers"
            ]
        )

        # One article is not enough.
        if len(publishers) < 2:
            continue

        combined = " ".join(
            group["titles"]
        )

        published = (
            min(
                group["dates"]
            )
            if group["dates"]
            else None
        )

        candidate = {
            "name": group["name"],
            "status": detect_status(
                combined,
                published
            ),
            "chain": detect_chain(
                combined
            ),
            "firstSeen": (
                published.date().isoformat()
                if published
                else TODAY
            ),
            "confidence": 0,
            "description": (
                group[
                    "titles"
                ][0][:320]
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
            "_publishers": publishers,
        }

        merge_candidate(
            pool,
            candidate
        )


# =========================================================
# PUBLIC DISCORD COMMUNITY INTELLIGENCE
# Cryptic Crypto = PRIORIDAD PRINCIPAL
# =========================================================

def discord_invite_code(invite):
    try:
        parsed = urllib.parse.urlparse(
            clean(invite)
        )

        parts = [
            value
            for value in parsed.path.split("/")
            if value
        ]

        if parts:
            return parts[-1]

    except Exception:
        pass

    return ""


def discord_source_info(source):

    invite = clean(
        source.get("invite")
    )

    code = discord_invite_code(
        invite
    )

    result = {
        "name": clean(
            source.get("name")
        ),
        "invite": invite,
        "code": code,
        "primary": bool(
            source.get("primary")
        ),
        "members": 0,
        "online": 0,
    }

    if not code:
        return result

    api_url = (
        "https://discord.com/api/v10/invites/"
        + urllib.parse.quote(
            code,
            safe=""
        )
        + "?with_counts=true"
    )

    data = safe_json(
        api_url,
        15
    )

    if isinstance(data, dict):

        guild = (
            data.get("guild")
            or {}
        )

        if not result["name"]:
            result["name"] = clean(
                guild.get("name")
            )

        result["members"] = int(
            data.get(
                "approximate_member_count",
                0
            )
            or 0
        )

        result["online"] = int(
            data.get(
                "approximate_presence_count",
                0
            )
            or 0
        )

    if not result["name"]:
        result["name"] = (
            "Discord " + code
        )

    return result


def scan_discord_public(
    pool,
    state,
    registry
):

    log(
        "Scanning public Discord community signals..."
    )

    resolved_sources = []

    for configured in DISCORD_WATCH_SOURCES:

        source = discord_source_info(
            configured
        )

        resolved_sources.append(
            source
        )

        community = clean(
            source.get("name")
        )

        primary = bool(
            source.get("primary")
        )

        if not community:
            continue

        if primary:
            log(
                "PRIMARY WATCH: "
                + community
            )
        else:
            log(
                "Discord watch: "
                + community
            )

        queries = [
            f'"{community}" "launchpad" crypto when:7d',
            f'"{community}" "token launch" crypto when:7d',
            f'"{community}" "launching soon" crypto when:7d',
        ]

        # Cryptic recibe búsquedas extra.
        if primary:
            queries.extend(
                [
                    f'"{community}" "new launchpad" when:7d',
                    f'"{community}" "memecoin launch" when:7d',
                    f'"{community}" "coming soon" crypto when:7d',
                    f'"{community}" "testnet" crypto when:7d',
                    f'"{community}" "bonding curve" crypto when:7d',
                ]
            )

        for query in queries:

            params = urllib.parse.urlencode(
                {
                    "q": query,
                    "hl": "en-US",
                    "gl": "US",
                    "ceid": "US:en",
                }
            )

            xml = safe_text(
                (
                    "https://news.google.com/"
                    "rss/search?"
                    + params
                ),
                20
            )

            if not xml:
                continue

            try:
                root = ET.fromstring(
                    xml
                )

            except Exception:
                continue

            for article in root.findall(
                ".//item"
            )[:30]:

                title = strip_publisher(
                    article.findtext(
                        "title"
                    )
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

                project_name = guess_news_name(
                    title
                )

                if not project_name:
                    continue

                if is_known_launchpad(
                    project_name
                ):
                    continue

                source_label = (
                    "Cryptic Public"
                    if primary
                    else (
                        "Discord Watch: "
                        + community
                    )
                )

                candidate = {
                    "name": project_name,
                    "status": detect_status(
                        title,
                        published
                    ),
                    "chain": detect_chain(
                        title
                    ),
                    "firstSeen": (
                        published.date().isoformat()
                        if published
                        else TODAY
                    ),
                    "confidence": 0,
                    "description": title[:320],
                    "website": "",
                    "x": "",
                    "discord": "",
                    "github": "",
                    "source": link,
                    "_sources": [
                        "News",
                        source_label,
                    ],
                    "_publishers": (
                        [publisher]
                        if publisher
                        else []
                    ),
                }

                merge_candidate(
                    pool,
                    candidate
                )

    state[
        "discord_sources"
    ] = resolved_sources
# =========================================================
# GITHUB
# =========================================================

def github_readme(full_name):
    data = safe_json(
        (
            "https://api.github.com/repos/"
            + urllib.parse.quote(
                full_name,
                safe="/"
            )
            + "/readme"
        ),
        25
    )

    if (
        not isinstance(
            data,
            dict
        )
        or not data.get(
            "content"
        )
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


def scan_github(
    pool,
    state,
    registry
):
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
            f'"token launcher" '
            f'in:name,description,readme '
            f'pushed:>={since}'
        ),
    )

    for query in queries:
        url = (
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
            url,
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
            if repo.get("fork"):
                continue

            if repo.get("archived"):
                continue

            full_name = clean(
                repo.get(
                    "full_name"
                )
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

            website = clean(
                repo.get(
                    "homepage"
                )
            )

            github_url = clean(
                repo.get(
                    "html_url"
                )
            )

            created = parse_date(
                repo.get(
                    "created_at"
                )
            )

            if any(
                bad in repo_name.lower()
                for bad in (
                    "tutorial",
                    "example",
                    "template",
                    "demo",
                    "course",
                    "homework",
                    "scraper",
                    "bot",
                )
            ):
                continue

            if not valid_project_domain(
                website
            ):
                continue

            readme = github_readme(
                full_name
            )

            repo_text = (
                repo_name
                + " "
                + description
                + " "
                + readme[:250000]
            )

            if not has_launch_signal(
                repo_text
            ):
                continue

            site = inspect_website(
                website
            )

            if not site[
                "reachable"
            ]:
                continue

            if not site[
                "launchSignal"
            ]:
                continue

            # Require official X or Discord.
            if not (
                site["x"]
                or site["discord"]
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

            if existing_nonlaunchpad(
                name,
                website,
                registry
            ):
                continue

            if (
                created
                and NOW - created
                > timedelta(days=45)
                and not site[
                    "prelaunchSignal"
                ]
            ):
                continue

            combined = (
                repo_text
                + " "
                + site["text"]
            )

            candidate = {
                "name": name,
                "status": detect_status(
                    combined,
                    created
                ),
                "chain": (
                    detect_chain(
                        repo_text
                    )
                    or site["chain"]
                ),
                "firstSeen": TODAY,
                "confidence": 0,
                "description": (
                    description[:320]
                    or (
                        f"{name} "
                        "launchpad candidate."
                    )
                ),
                "website": website,
                "x": site["x"],
                "discord": (
                    site["discord"]
                ),
                "github": github_url,
                "source": github_url,
                "_sources": [
                    "GitHub",
                    "Website"
                ],
                "_publishers": [],
            }

            merge_candidate(
                pool,
                candidate
            )


# =========================================================
# DEFILLAMA NEW LAUNCHPADS
# =========================================================

def scan_defillama(
    pool,
    state,
    registry
):
    current = set(
        registry[
            "launchpadIds"
        ]
    )

    old = set(
        state.get(
            "defillama_v5_seen",
            []
        )
    )

    if not old:
        state[
            "defillama_v5_seen"
        ] = sorted(current)

        return

    new_ids = current - old

    for protocol in registry[
        "protocols"
    ]:
        if (
            protocol["id"]
            not in new_ids
        ):
            continue

        name = protocol[
            "name"
        ]

        website = protocol[
            "website"
        ]

        if not valid_project_domain(
            website
        ):
            continue

        if is_known_launchpad(
            name,
            website
        ):
            continue

        site = inspect_website(
            website
        )

        if not site[
            "reachable"
        ]:
            continue

        x_url = site["x"]

        twitter = protocol[
            "twitter"
        ]

        if (
            twitter
            and not x_url
        ):
            x_url = (
                twitter
                if twitter.startswith(
                    "http"
                )
                else (
                    "https://x.com/"
                    + twitter.lstrip("@")
                )
            )

        chains = protocol[
            "chains"
        ]

        chain = (
            ", ".join(
                str(value)
                for value in chains[:4]
            )
            if isinstance(
                chains,
                list
            )
            else clean(chains)
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
                protocol[
                    "description"
                ][:320]
                or (
                    "New DefiLlama "
                    "launchpad."
                )
            ),
            "website": website,
            "x": x_url,
            "discord": (
                site["discord"]
            ),
            "github": (
                site["github"]
            ),
            "source": (
                "https://defillama.com/"
                "protocol/"
                + urllib.parse.quote(
                    protocol["slug"]
                )
            ),
            "_sources": [
                "DefiLlama",
                "Website"
            ],
            "_publishers": [],
        }

        merge_candidate(
            pool,
            candidate
        )

    state[
        "defillama_v5_seen"
    ] = sorted(current)


# =========================================================
# DEX SCREENER
# =========================================================

def dex_links(profile):
    raw = ""

    for link in (
        profile.get(
            "links"
        )
        or []
    ):
        if isinstance(
            link,
            dict
        ):
            raw += (
                "\n"
                + clean(
                    link.get(
                        "url"
                    )
                )
            )

    return extract_links(
        raw
    )


def scan_dex(
    pool,
    state,
    registry
):
    log(
        "Scanning new DEX profiles..."
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

    old = set(
        state.get(
            "dex_v5_seen",
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

    if not old:
        state[
            "dex_v5_seen"
        ] = sorted(current)

        return

    all_seen = set(old)

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

        if identity in old:
            continue

        links = dex_links(
            profile
        )

        website = links[
            "website"
        ]

        if not valid_project_domain(
            website
        ):
            continue

        site = inspect_website(
            website
        )

        if not site[
            "reachable"
        ]:
            continue

        if not site[
            "launchSignal"
        ]:
            continue

        if not (
            site["x"]
            or site["discord"]
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

        if existing_nonlaunchpad(
            name,
            website,
            registry
        ):
            continue

        description = clean(
            profile.get(
                "description"
            )
        )

        # Reject explicit negative language.
        if any(
            re.search(
                pattern,
                description.lower()
            )
            for pattern in NEGATIVE_PATTERNS
        ):
            continue

        candidate = {
            "name": name,
            "status": detect_status(
                site["text"]
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
                    f"{name} new "
                    "on-chain candidate."
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

        merge_candidate(
            pool,
            candidate
        )

    state[
        "dex_v5_seen"
    ] = list(
        all_seen
    )[-5000:]


# =========================================================
# CONFIDENCE
# =========================================================

def confidence(item):
    if item.get(
        "pinned"
    ):
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
        score += 15

    if "DEX Screener" in sources:
        score += 30

    if "DefiLlama" in sources:
        score += 50

    if "News" in sources:
        score += min(
            30,
            len(publishers) * 10
        )
    # Cryptic Crypto = fuente principal
    if "Cryptic Public" in sources:
        score += 20

    # Otros Discord = fuentes secundarias
    if any(
        source.startswith("Discord Watch:")
        for source in sources
    ):
        score += 8
    if item.get("x"):
        score += 8

    if item.get("discord"):
        score += 8

    if item.get("github"):
        score += 4

    if item.get("status") in {
        "COMING SOON",
        "TESTNET",
        "ANNOUNCED",
    }:
        score += 5

    return min(
        score,
        100
    )


# =========================================================
# TIER
# =========================================================

def tier(item):
    if item.get(
        "pinned"
    ):
        return "KNOWN"

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

    score = confidence(
        item
    )

    news2 = (
        "News" in sources
        and len(publishers) >= 2
    )

    site = (
        "Website" in sources
    )

    github = (
        "GitHub" in sources
    )

    dex = (
        "DEX Screener" in sources
    )

    llama = (
        "DefiLlama" in sources
    )

    if (
        llama
        and site
        and score >= 80
    ):
        return "VERIFIED"

    if (
        site
        and github
        and dex
        and score >= 80
    ):
        return "VERIFIED"

    if (
        site
        and github
        and news2
        and score >= 80
    ):
        return "VERIFIED"

    if (
        site
        and dex
        and news2
        and score >= 80
    ):
        return "VERIFIED"

    if (
        site
        and (
            github
            or dex
        )
        and score >= 65
    ):
        return "WATCHLIST"

    return ""


# =========================================================
# FINAL
# =========================================================

def finalize(
    pool,
    registry
):
    verified = []
    watchlist = []
    known = []

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

        if (
            not item.get(
                "pinned"
            )
            and is_known_launchpad(
                name,
                website
            )
        ):
            continue

        if (
            not item.get(
                "pinned"
            )
            and existing_nonlaunchpad(
                name,
                website,
                registry
            )
        ):
            continue

        radar_tier = tier(
            item
        )

        if not radar_tier:
            continue

        publishers = list(
            dict.fromkeys(
                item.get(
                    "_publishers",
                    []
                )
            )
        )

        sources = list(
            dict.fromkeys(
                item.get(
                    "_sources",
                    []
                )
            )
        )

        labels = []

        for source in sources:
            if source == "News":
                labels.append(
                    (
                        "News "
                        f"({len(publishers)} "
                        "publishers)"
                    )
                )

            else:
                labels.append(
                    source
                )

        item[
            "radarTier"
        ] = radar_tier

        item[
            "confidence"
        ] = confidence(
            item
        )

        item[
            "detectedBy"
        ] = " + ".join(
            labels
        )

        item[
            "scannerVersion"
        ] = SCANNER_VERSION

        item[
            "lastConfirmed"
        ] = TODAY

        item.pop(
            "_sources",
            None
        )

        item.pop(
            "_publishers",
            None
        )

        if radar_tier == "VERIFIED":
            verified.append(
                item
            )

        elif radar_tier == "WATCHLIST":
            watchlist.append(
                item
            )

        else:
            known.append(
                item
            )

    sort_key = lambda item: (
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

    verified.sort(
        key=sort_key
    )

    watchlist.sort(
        key=sort_key
    )

    known.sort(
        key=sort_key
    )

    return (
        verified,
        watchlist,
        known
    )


# =========================================================
# MAIN
# =========================================================

def main():
    log(
        "Starting Launchpad Intelligence Radar v5..."
    )

    pool = load_history()

    state = load_json(
        STATE_FILE,
        {}
    )

    previous_version = int(
        state.get(
            "scanner_version",
            0
        )
        or 0
    )

    # Fresh baseline on first v5 execution.
    if previous_version < SCANNER_VERSION:
        state[
            "dex_v5_seen"
        ] = []

        state[
            "defillama_v5_seen"
        ] = []

    registry = (
        build_defillama_registry()
    )

    try:
        scan_news(
            pool,
            state,
            registry
        )

    except Exception as error:
        log(
            f"News error: {error}"
        )
    try:
        scan_discord_public(
            pool,
            state,
            registry
        )

    except Exception as error:
        log(
            f"Discord public intelligence error: {error}"
        )
    try:
        scan_github(
            pool,
            state,
            registry
        )

    except Exception as error:
        log(
            f"GitHub error: {error}"
        )

    try:
        scan_dex(
            pool,
            state,
            registry
        )

    except Exception as error:
        log(
            f"DEX Screener error: {error}"
        )

    try:
        scan_defillama(
            pool,
            state,
            registry
        )

    except Exception as error:
        log(
            f"DefiLlama error: {error}"
        )

    (
        verified,
        watchlist,
        known
    ) = finalize(
        pool,
        registry
    )

    updated = (
        NOW.isoformat(
            timespec="seconds"
        )
        .replace(
            "+00:00",
            "Z"
        )
    )

    database = {
        "updatedAt": updated,
        "scannerVersion": SCANNER_VERSION,
        "verified": verified,
        "watchlist": watchlist,
        "known": known,
        "launchpads": (
            verified
            + watchlist
            + known
        ),
    }

    save_json(
        DB_FILE,
        database
    )

    state[
        "scanner_version"
    ] = SCANNER_VERSION

    state[
        "last_run"
    ] = updated

    save_json(
        STATE_FILE,
        state
    )

    log(
        (
            f"Finished: "
            f"{len(verified)} VERIFIED, "
            f"{len(watchlist)} WATCHLIST, "
            f"{len(known)} KNOWN."
        )
    )


if __name__ == "__main__":
    main()
