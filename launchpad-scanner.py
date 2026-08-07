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
# LAUNCHPAD INTELLIGENCE RADAR v4
# =========================================================
#
# VERIFIED:
#   Evidencia fuerte e independiente.
#
# WATCHLIST:
#   Proyecto posible, pero todavía sin confirmación suficiente.
#
# KNOWN:
#   Launchpads ya conocidas como Pools.trade.
#
# FUENTES:
#   - Google News
#   - GitHub
#   - DefiLlama
#   - DEX Screener
#   - Websites oficiales
#
# =========================================================


DB_FILE = Path("launchpad-intel.json")
STATE_FILE = Path("launchpad-scanner-state.json")

SCANNER_VERSION = 4

NOW = datetime.now(timezone.utc)
TODAY = NOW.date().isoformat()

USER_AGENT = "ProjectLabSol-Launchpad-Radar/4.0"
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
    "on-chain",
    "onchain",
)

PRELAUNCH_TERMS = (
    "coming soon",
    "launching soon",
    "pre-launch",
    "prelaunch",
    "waitlist",
    "testnet",
    "early access",
    "will launch",
    "plans to launch",
    "launch soon",
)

GENERIC_NAMES = {
    "new",
    "crypto",
    "cryptocurrency",
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
}


# =========================================================
# KNOWN LAUNCHPADS
# Estas no pueden aparecer como descubrimientos nuevos.
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
# MEDIA / NON PROJECT
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

NON_PROJECT_DOMAINS = {
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
}

BAD_PAGE_PATHS = (
    "/blog/",
    "/article/",
    "/articles/",
    "/post/",
    "/posts/",
    "/news/",
    "/tutorial/",
    "/tutorials/",
    "/course/",
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
    host = get_host(url)

    return bool(
        host
        and domain_matches(
            host,
            MEDIA_DOMAINS
        )
    )


def is_known_launchpad(name="", website=""):
    name_key = normalize(name)
    host = get_host(website)

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

    host = get_host(url)

    if not host:
        return False

    if domain_matches(
        host,
        MEDIA_DOMAINS | NON_PROJECT_DOMAINS
    ):
        return False

    parsed = urllib.parse.urlparse(url)

    path = (
        parsed.path
        or "/"
    ).lower()

    if any(
        value in path
        for value in BAD_PAGE_PATHS
    ):
        return False

    segments = [
        part
        for part in path.split("/")
        if part
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
# JSON
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
# SIGNALS
# =========================================================

def has_launch_signal(text):
    low = clean(text).lower()

    launch = any(
        value in low
        for value in LAUNCH_TERMS
    )

    crypto = any(
        value in low
        for value in CRYPTO_TERMS
    )

    return launch and crypto


def has_prelaunch_signal(text):
    low = clean(text).lower()

    return any(
        value in low
        for value in PRELAUNCH_TERMS
    )


def detect_chain(text):
    low = (
        " "
        + clean(text).lower()
        + " "
    )

    networks = (
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
    )

    result = []

    for name, aliases in networks:
        if any(
            alias in low
            for alias in aliases
        ):
            result.append(name)

    return ", ".join(
        result[:3]
    )


# =========================================================
# STATUS
# =========================================================

def detect_status(text, published=None):
    low = clean(text).lower()

    if "testnet" in low:
        return "TESTNET"

    if any(
        value in low
        for value in (
            "coming soon",
            "launching soon",
            "pre-launch",
            "prelaunch",
            "launch soon"
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

    for raw_url in urls:
        url = raw_url.rstrip(
            ".,;:"
        )

        host = get_host(url)
        low = url.lower()

        if not host:
            continue

        # X
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
                    (
                        r"^https?://"
                        r"(?:www\.)?"
                        r"twitter\.com/"
                    ),
                    "https://x.com/",
                    url,
                    flags=re.I
                )

            continue

        # Discord
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

        # GitHub
        if host == "github.com":
            if not result["github"]:
                result["github"] = url

            continue

        # Website
        if (
            is_project_homepage(url)
            and not result["website"]
        ):
            result["website"] = url

    return result


# =========================================================
# WEBSITE VERIFICATION
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

    text = clean(
        re.sub(
            r"<[^>]+>",
            " ",
            html[:800000]
        )
    )[:35000]

    combined = (
        html[:800000]
        + "\n"
        + text
    )

    result["text"] = text

    result["launchSignal"] = (
        has_launch_signal(
            combined
        )
    )

    result["prelaunchSignal"] = (
        has_prelaunch_signal(
            combined
        )
    )

    result["chain"] = (
        detect_chain(
            combined
        )
    )

    links = extract_links(
        combined
    )

    result["x"] = links["x"]
    result["discord"] = links["discord"]
    result["github"] = links["github"]

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

    special_tlds = {
        "trade",
        "fun",
        "xyz",
        "fi",
        "app",
        "gg",
        "zone",
    }

    if parts[-1] in special_tlds:
        return (
            f"{parts[-2]}.{parts[-1]}"
        )

    return (
        parts[-2]
        .replace("-", " ")
        .title()
    )


# =========================================================
# DEFILLAMA REGISTRY
# =========================================================

def build_defillama_registry():
    log(
        "Loading DefiLlama protocol registry..."
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
                protocol.get("chains")
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
                protocol.get("slug")
                or name
            ),
        }

        registry["protocols"].append(
            entry
        )

        name_key = normalize(name)

        if name_key:
            registry["byName"][
                name_key
            ] = entry

        host = get_host(
            website
        )

        if host:
            registry["byDomain"][
                host
            ] = entry

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

    if (
        name_key
        and name_key
        in registry["byName"]
    ):
        return registry[
            "byName"
        ][name_key]

    host = get_host(
        website
    )

    if not host:
        return None

    for known_host, protocol in (
        registry["byDomain"].items()
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


def is_existing_nonlaunchpad(
    name,
    website,
    registry
):
    protocol = find_defillama_protocol(
        name,
        website,
        registry
    )

    if not protocol:
        return False

    category = (
        protocol["category"]
        .lower()
    )

    if "launchpad" not in category:
        log(
            (
                "Ignoring existing "
                f"{protocol['category']} protocol: "
                f"{protocol['name']}"
            )
        )

        return True

    return False


# =========================================================
# IDENTITY / MERGE
# =========================================================

def identity_tokens(item):
    tokens = set()

    name = normalize(
        item.get(
            "name",
            ""
        )
    )

    if name:
        tokens.add(name)

    host = get_host(
        item.get(
            "website",
            ""
        )
    )

    if host:
        tokens.add(
            normalize(host)
        )

        stem = host.split(".")[0]

        if len(stem) >= 4:
            tokens.add(
                normalize(stem)
            )

    return tokens


def merge_candidate(
    pool,
    candidate
):
    candidate_tokens = (
        identity_tokens(
            candidate
        )
    )

    if not candidate_tokens:
        return

    matched_key = None

    for key, existing in pool.items():
        if (
            candidate_tokens
            & identity_tokens(existing)
        ):
            matched_key = key
            break

    if matched_key is None:
        matched_key = sorted(
            candidate_tokens
        )[0]

        pool[matched_key] = (
            candidate
        )

        return

    current = pool[
        matched_key
    ]

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

    old_status = current.get(
        "status",
        "RUMOR"
    )

    new_status = candidate.get(
        "status",
        "RUMOR"
    )

    if (
        ranking.get(
            new_status,
            0
        )
        >
        ranking.get(
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
            and candidate.get(field)
        ):
            current[field] = (
                candidate[field]
            )


# =========================================================
# POOLS.TRADE KNOWN
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
        "website": "https://pools.trade/",
        "x": site["x"],
        "discord": site["discord"],
        "github": site["github"],
        "source": "https://pools.trade/",
        "detectedBy": "Known platform",
        "scannerVersion": SCANNER_VERSION,
        "pinned": True,
        "_sources": [
            "Known platform"
        ],
        "_publishers": [],
    }


# =========================================================
# LOAD V4 HISTORY
# v1/v2/v3 se eliminan automáticamente.
# =========================================================

def load_history():
    database = load_json(
        DB_FILE,
        {
            "launchpads": []
        }
    )

    pool = {}

    merge_candidate(
        pool,
        pools_trade_record()
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
        ) < SCANNER_VERSION:
            continue

        if int(
            item.get(
                "confidence",
                0
            )
            or 0
        ) < 65:
            continue

        clone = dict(
            item
        )

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

        merge_candidate(
            pool,
            clone
        )

    return pool


# =========================================================
# NEWS
# =========================================================

def strip_news_publisher(title):
    return re.sub(
        r"\s+-\s+[^-]{2,100}$",
        "",
        clean(title)
    ).strip()


def guess_news_name(title):
    title = strip_news_publisher(
        title
    )

    domain_match = re.search(
        (
            r"\b("
            r"[a-z0-9]"
            r"[a-z0-9-]{1,35}"
            r"\."
            r"(?:trade|fun|xyz|io|app|fi|gg|zone)"
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
            r"(?:memecoin\s+|token\s+)?"
            r"launchpad\b"
        ),
        (
            r"\b"
            r"(?:launches|unveils|introduces|reveals|announces)"
            r"\s+"
            r"(?:new\s+|its\s+)*"
            r"([A-Z][A-Za-z0-9._-]{2,40})"
        ),
    )

    generic = {
        normalize(value)
        for value in GENERIC_NAMES
    }

    for pattern in patterns:
        match = re.search(
            pattern,
            title
        )

        if not match:
            continue

        candidate = clean(
            match.group(1)
        ).strip(
            ".,:-"
        )

        if (
            normalize(candidate)
            not in generic
        ):
            return candidate

    return ""


def website_from_name(name):
    value = clean(
        name
    ).lower()

    if re.fullmatch(
        (
            r"[a-z0-9]"
            r"[a-z0-9-]{1,35}"
            r"\."
            r"(?:trade|fun|xyz|io|app|fi|gg|zone)"
        ),
        value
    ):
        url = (
            "https://"
            + value
        )

        if is_project_homepage(
            url
        ):
            return url

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
        '"memecoin launchpad" when:3d',
        '"new launchpad" crypto when:3d',
        '"coming soon" launchpad crypto when:7d',
        '"testnet" launchpad token when:7d',
        '"token launch platform" when:3d',
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
                "ceid": "US:en",
            }
        )

        feed = (
            "https://news.google.com/"
            "rss/search?"
            + params
        )

        xml = safe_text(
            feed,
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

            title = strip_news_publisher(
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

            if link:
                seen.add(
                    link
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

            website = website_from_name(
                name
            )

            if is_existing_nonlaunchpad(
                name,
                website,
                registry
            ):
                continue

            key = normalize(name)

            if key not in grouped:
                grouped[key] = {
                    "name": name,
                    "website": website,
                    "titles": [],
                    "publishers": set(),
                    "links": [],
                    "dates": [],
                }

            grouped[key][
                "titles"
            ].append(
                title
            )

            if publisher:
                grouped[key][
                    "publishers"
                ].add(
                    publisher
                )

            if link:
                grouped[key][
                    "links"
                ].append(
                    link
                )

            if published:
                grouped[key][
                    "dates"
                ].append(
                    published
                )

    for group in grouped.values():
        combined = " ".join(
            group["titles"]
        )

        published = (
            min(group["dates"])
            if group["dates"]
            else None
        )

        website = group[
            "website"
        ]

        links = {
            "x": "",
            "discord": "",
            "github": "",
        }

        sources = [
            "News"
        ]

        if website:
            site = inspect_website(
                website
            )

            if (
                site["reachable"]
                and site["launchSignal"]
            ):
                sources.append(
                    "Website"
                )

                links["x"] = site["x"]
                links["discord"] = (
                    site["discord"]
                )
                links["github"] = (
                    site["github"]
                )

            else:
                website = ""

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
                group["titles"][0][:320]
            ),
            "website": website,
            "x": links["x"],
            "discord": links["discord"],
            "github": links["github"],
            "source": (
                group["links"][0]
                if group["links"]
                else ""
            ),
            "_sources": sources,
            "_publishers": sorted(
                group["publishers"]
            ),
        }

        merge_candidate(
            pool,
            candidate
        )

    state["news_seen"] = list(
        seen
    )[-3000:]


# =========================================================
# GITHUB
# =========================================================

def read_github_readme(full_name):
    endpoint = (
        "https://api.github.com/"
        "repos/"
        + urllib.parse.quote(
            full_name,
            safe="/"
        )
        + "/readme"
    )

    data = safe_json(
        endpoint,
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
                )
            ):
                continue

            if not is_project_homepage(
                website
            ):
                continue

            readme = read_github_readme(
                full_name
            )

            combined = (
                repo_name
                + " "
                + description
                + "\n"
                + readme[:250000]
            )

            if not has_launch_signal(
                combined
            ):
                continue

            site = inspect_website(
                website
            )

            if not site["reachable"]:
                continue

            if not site["launchSignal"]:
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

            if is_existing_nonlaunchpad(
                name,
                website,
                registry
            ):
                continue

            candidate = {
                "name": name,
                "status": detect_status(
                    combined
                    + " "
                    + site["text"]
                ),
                "chain": (
                    site["chain"]
                    or detect_chain(
                        combined
                    )
                ),
                "firstSeen": TODAY,
                "confidence": 0,
                "description": (
                    description[:320]
                    or (
                        f"{name} is being "
                        "tracked as an "
                        "unverified launchpad candidate."
                    )
                ),
                "website": website,
                "x": site["x"],
                "discord": site["discord"],
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

    state["github_seen"] = list(
        seen
    )[-3500:]


# =========================================================
# DEFILLAMA NEW LAUNCHPADS
# =========================================================

def scan_defillama_new(
    pool,
    state,
    registry
):
    log(
        "Checking new DefiLlama launchpads..."
    )

    current_ids = set(
        registry[
            "launchpadIds"
        ]
    )

    old_ids = set(
        state.get(
            "defillama_launchpad_seen",
            []
        )
    )

    if not old_ids:
        state[
            "defillama_launchpad_seen"
        ] = sorted(
            current_ids
        )

        return

    new_ids = (
        current_ids
        - old_ids
    )

    for protocol in registry[
        "protocols"
    ]:
        if protocol[
            "id"
        ] not in new_ids:
            continue

        name = protocol[
            "name"
        ]

        website = protocol[
            "website"
        ]

        if not is_project_homepage(
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

        if not site["reachable"]:
            continue

        twitter = protocol[
            "twitter"
        ]

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

        chains = protocol[
            "chains"
        ]

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
                    protocol["slug"]
                )
            ),
            "_sources": [
                "DefiLlama",
                "Website",
            ],
            "_publishers": [],
        }

        merge_candidate(
            pool,
            candidate
        )

    state[
        "defillama_launchpad_seen"
    ] = sorted(
        current_ids
    )


# =========================================================
# DEX SCREENER
# =========================================================

def dex_links(profile):
    text = ""

    for item in (
        profile.get(
            "links"
        )
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

    return extract_links(
        text
    )


def scan_dexscreener(
    pool,
    state,
    registry
):
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

    if not old_seen:
        state[
            "dex_profiles_seen"
        ] = sorted(
            current
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

        links = dex_links(
            profile
        )

        website = links[
            "website"
        ]

        if not is_project_homepage(
            website
        ):
            continue

        site = inspect_website(
            website
        )

        if not site["reachable"]:
            continue

        if not site["launchSignal"]:
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

        if is_existing_nonlaunchpad(
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

        candidate = {
            "name": name,
            "status": detect_status(
                description
                + " "
                + site["text"]
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
                    f"{name} has new "
                    "on-chain launchpad signals."
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
        "dex_profiles_seen"
    ] = list(
        all_seen
    )[-4000:]


# =========================================================
# CONFIDENCE
# =========================================================

def calculate_confidence(item):
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
        score += 25

    if "DefiLlama" in sources:
        score += 45

    if "News" in sources:
        score += 10

        score += min(
            20,
            max(
                0,
                len(publishers) - 1
            ) * 10
        )

    if item.get("website"):
        score += 5

    if item.get("x"):
        score += 8

    if item.get("discord"):
        score += 8

    if item.get("github"):
        score += 5

    if item.get("status") in {
        "COMING SOON",
        "TESTNET",
        "ANNOUNCED"
    }:
        score += 7

    return min(
        score,
        100
    )


# =========================================================
# TIER
# =========================================================

def determine_tier(item):
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

    score = calculate_confidence(
        item
    )

    news_confirmed = (
        "News" in sources
        and len(publishers) >= 2
    )

    github = (
        "GitHub" in sources
    )

    dex = (
        "DEX Screener"
        in sources
    )

    llama = (
        "DefiLlama" in sources
    )

    website = (
        "Website" in sources
    )

    # VERIFIED

    if (
        llama
        and website
        and score >= 80
    ):
        return "VERIFIED"

    if (
        website
        and github
        and news_confirmed
        and score >= 80
    ):
        return "VERIFIED"

    if (
        website
        and dex
        and news_confirmed
        and score >= 80
    ):
        return "VERIFIED"

    if (
        website
        and dex
        and github
        and score >= 80
    ):
        return "VERIFIED"

    # WATCHLIST

    if (
        website
        and (
            github
            or dex
            or news_confirmed
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
                "name",
                ""
            )
        )

        website = clean(
            item.get(
                "website",
                ""
            )
        )

        if not name:
            continue

        if is_media_url(
            website
        ):
            continue

        if (
            not item.get("pinned")
            and is_known_launchpad(
                name,
                website
            )
        ):
            continue

        if (
            not item.get("pinned")
            and is_existing_nonlaunchpad(
                name,
                website,
                registry
            )
        ):
            continue

        tier = determine_tier(
            item
        )

        if not tier:
            continue

        score = calculate_confidence(
            item
        )

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
                        "News "
                        f"({len(publishers)} publishers)"
                    )
                )

            else:
                labels.append(
                    source
                )

        item[
            "radarTier"
        ] = tier

        item[
            "confidence"
        ] = score

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

        if tier == "VERIFIED":
            verified.append(
                item
            )

        elif tier == "WATCHLIST":
            watchlist.append(
                item
            )

        elif tier == "KNOWN":
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
        "Starting Launchpad Intelligence Radar v4..."
    )

    pool = load_history()

    state = load_json(
        STATE_FILE,
        {}
    )

    registry = (
        build_defillama_registry()
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
            "DEX Screener",
            scan_dexscreener
        ),
    )

    for label, scanner in scanners:
        try:
            scanner(
                pool,
                state,
                registry
            )

        except Exception as error:
            log(
                f"{label} error: {error}"
            )

    try:
        scan_defillama_new(
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

    updated = NOW.isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )

    all_items = (
        verified
        + watchlist
        + known
    )

    database = {
        "updatedAt": updated,
        "scannerVersion": SCANNER_VERSION,
        "verified": verified,
        "watchlist": watchlist,
        "known": known,
        "launchpads": all_items,
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
