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
# LAUNCHPAD INTELLIGENCE SCANNER v2
# =========================================================
#
# Busca señales públicas en:
# - Google News
# - GitHub
# - DefiLlama
# - DEX Screener
#
# También intenta encontrar:
# - Website
# - X / Twitter
# - Discord
# - GitHub
#
# IMPORTANTE:
# No lee mensajes privados de Discord.
# No usa la API completa de X.
# Solo extrae enlaces públicos disponibles.
# =========================================================


DB_FILE = Path("launchpad-intel.json")
STATE_FILE = Path("launchpad-scanner-state.json")

SCANNER_VERSION = 2

NOW = datetime.now(timezone.utc)
TODAY = NOW.date().isoformat()

USER_AGENT = "ProjectLabSol-Launchpad-Radar/2.0"

GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN",
    ""
).strip()


# =========================================================
# PALABRAS CLAVE
# =========================================================

LAUNCH_WORDS = (
    "launchpad",
    "memecoin launch",
    "meme coin launch",
    "token launch platform",
    "bonding curve",
    "fair launch",
    "token launcher",
    "coin launcher"
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
    "official"
}


# =========================================================
# LAUNCHPADS YA CONOCIDAS
# =========================================================
#
# Estas NO deben volver a aparecer como
# "nueva launchpad".
# =========================================================

KNOWN_LAUNCHPADS = {
    "pumpfun",
    "pumpswap",
    "raydium",
    "fourmeme",
    "pools",
    "poolstrade",
    "bonkfun",
    "letsbonk",
    "moonshot",
    "believe",
    "bags",
    "bagsfm",
    "boop",
    "moonit",
    "daosfun",
    "clanker",
    "grafun",
    "virtuals",
    "flaunch"
}


# Pools.trade sí queremos conservarla
# como plataforma conocida / LIVE.

PINNED_KNOWN = {
    "poolstrade"
}


# =========================================================
# MEDIOS DE NOTICIAS
# =========================================================
#
# Estos dominios jamás deben convertirse
# en nombre de launchpad.
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
    "bloomberg.com"
}


# =========================================================
# HELPERS
# =========================================================

def log(message):

    print(
        "[RADAR]",
        message
    )


def clean(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def norm(name):

    return re.sub(
        r"[^a-z0-9]+",
        "",
        clean(name).lower()
    )


def domain(url):

    try:

        host = urllib.parse.urlparse(
            url
        ).netloc.lower()

        host = host.split("@")[-1]
        host = host.split(":")[0]

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:

        return ""


def domain_matches(
    host,
    domains
):

    return any(
        host == item
        or host.endswith(
            "." + item
        )
        for item in domains
    )


def is_media(url):

    host = domain(
        url
    )

    if not host:
        return False

    return domain_matches(
        host,
        MEDIA_DOMAINS
    )


# =========================================================
# HTTP
# =========================================================

def request_headers(url):

    result = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*"
    }

    if "api.github.com" in url:

        result["Accept"] = (
            "application/vnd.github+json"
        )

        result["X-GitHub-Api-Version"] = (
            "2022-11-28"
        )

        if GITHUB_TOKEN:

            result["Authorization"] = (
                f"Bearer {GITHUB_TOKEN}"
            )

    return result


def fetch_text(
    url,
    timeout=20
):

    request = urllib.request.Request(
        url,
        headers=request_headers(
            url
        )
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def safe_text(
    url,
    timeout=20
):

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


def safe_json(
    url,
    timeout=25
):

    try:

        text = fetch_text(
            url,
            timeout
        )

        return json.loads(
            text
        )

    except Exception as error:

        log(
            f"Could not read JSON {url}: {error}"
        )

        return None


# =========================================================
# ARCHIVOS JSON
# =========================================================

def load_json(
    path,
    default
):

    try:

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return default


def save_json(
    path,
    data
):

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ) + "\n",
        encoding="utf-8"
    )


# =========================================================
# FECHAS
# =========================================================

def parse_date(value):

    value = clean(
        value
    )

    if not value:

        return None

    formats = (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d"
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
# DETECCIÓN
# =========================================================

def is_launch_signal(text):

    low = clean(
        text
    ).lower()

    if not any(
        word in low
        for word in LAUNCH_WORDS
    ):

        return False

    crypto_words = (
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
        "defi",
        "on-chain",
        "onchain"
    )

    return any(
        word in low
        for word in crypto_words
    )


def detect_chain(text):

    low = clean(
        text
    ).lower()

    patterns = (
        (
            "Robinhood Chain",
            (
                "robinhood chain",
            )
        ),
        (
            "Solana",
            (
                "solana",
            )
        ),
        (
            "Base",
            (
                "base chain",
                "on base",
                "base network"
            )
        ),
        (
            "BNB Chain",
            (
                "bnb chain",
                "bsc",
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
            (
                "arbitrum",
            )
        ),
        (
            "Polygon",
            (
                "polygon",
            )
        ),
        (
            "Avalanche",
            (
                "avalanche",
            )
        ),
        (
            "Optimism",
            (
                "optimism",
            )
        )
    )

    detected = []

    for name, words in patterns:

        if any(
            word in low
            for word in words
        ):

            detected.append(
                name
            )

    return ", ".join(
        detected[:3]
    )


# =========================================================
# STATUS
# =========================================================

def status_from_text(
    text,
    published=None
):

    low = clean(
        text
    ).lower()

    if (
        "testnet" in low
        or "beta test" in low
    ):

        return "TESTNET"

    if any(
        item in low
        for item in (
            "coming soon",
            "launching soon",
            "pre-launch",
            "prelaunch"
        )
    ):

        return "COMING SOON"

    if any(
        item in low
        for item in (
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
        item in low
        for item in (
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
            <= timedelta(
                hours=72
            )
        ):

            return "NEW"

        return "LIVE"

    return "RUMOR"


# =========================================================
# GOOGLE NEWS
# =========================================================

def strip_publisher(title):

    return re.sub(
        r"\s+-\s+[^-]{2,100}$",
        "",
        clean(title)
    ).strip()


# =========================================================
# LINKS
# =========================================================

def public_links(text):

    result = {
        "website": "",
        "x": "",
        "discord": "",
        "github": ""
    }

    if not text:

        return result

    urls = re.findall(
        r"https?://[^\s<>'\"\)\]\}]+",
        text,
        flags=re.I
    )

    ignored_domains = (
        MEDIA_DOMAINS
        | {
            "github.com",
            "x.com",
            "twitter.com",
            "discord.gg",
            "discord.com",
            "t.me",
            "telegram.me",
            "dexscreener.com",
            "defillama.com",
            "shields.io",
            "img.shields.io",
            "youtube.com",
            "youtu.be"
        }
    )

    for raw_url in urls:

        url = raw_url.rstrip(
            ".,;:"
        )

        host = domain(
            url
        )

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

                result["x"] = url

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

        if domain_matches(
            host,
            ignored_domains
        ):

            continue

        if not result["website"]:

            result["website"] = url

    return result


def inspect_site(
    website,
    extra=""
):

    links = public_links(
        extra
    )

    if (
        website
        and website.startswith(
            (
                "http://",
                "https://"
            )
        )
        and not is_media(
            website
        )
    ):

        page = safe_text(
            website,
            12
        )

        page_links = public_links(
            page[:700000]
        )

        for key in (
            "x",
            "discord",
            "github"
        ):

            if (
                not links[key]
                and page_links[key]
            ):

                links[key] = (
                    page_links[key]
                )

        links["website"] = (
            website
        )

    return links


# =========================================================
# NOMBRE DESDE DOMINIO
# =========================================================

def name_from_domain(url):

    host = domain(
        url
    )

    if not host:

        return ""

    parts = host.split(
        "."
    )

    if len(parts) < 2:

        return ""

    stem = parts[-2]
    tld = parts[-1]

    if tld in {
        "trade",
        "fun",
        "xyz",
        "fi",
        "app"
    }:

        return (
            f"{stem}.{tld}"
        )

    return stem.replace(
        "-",
        " "
    ).title()


# =========================================================
# DETECTAR NOMBRE EN NOTICIAS
# =========================================================

def guess_news_name(title):

    title = strip_publisher(
        title
    )

    # Ejemplo:
    # futurepad.trade

    domain_match = re.search(
        r"\b("
        r"[a-z0-9]"
        r"[a-z0-9-]{1,35}"
        r"\."
        r"(?:trade|fun|xyz|io|app|finance|fi|com)"
        r")\b",
        title,
        flags=re.I
    )

    if domain_match:

        candidate = (
            domain_match.group(
                1
            )
        )

        candidate_url = (
            "https://"
            + candidate
        )

        if not is_media(
            candidate_url
        ):

            return candidate

    patterns = (

        r"\b"
        r"(?:launches|unveils|introduces|reveals|announces|debuts)"
        r"\s+"
        r"(?:its\s+|the\s+|a\s+|an\s+|new\s+)*"
        r"([A-Z][A-Za-z0-9._-]{2,40})"
        r"\s+"
        r"(?:memecoin\s+|meme\s+coin\s+|token\s+)?"
        r"launchpad\b",

        r"\b"
        r"([A-Z][A-Za-z0-9._-]{2,40})"
        r"\s+"
        r"(?:memecoin\s+|meme\s+coin\s+|token\s+)?"
        r"launchpad\b"
    )

    generic_normalized = {
        norm(item)
        for item in GENERIC_NAMES
    }

    for pattern in patterns:

        match = re.search(
            pattern,
            title
        )

        if not match:

            continue

        candidate = clean(
            match.group(
                1
            )
        ).strip(
            ".,:-"
        )

        if norm(
            candidate
        ) in generic_normalized:

            continue

        return candidate

    return ""


def website_from_name(name):

    value = clean(
        name
    ).lower()

    if re.fullmatch(
        r"[a-z0-9]"
        r"[a-z0-9-]{1,35}"
        r"\."
        r"(?:trade|fun|xyz|io|app|finance|fi|com)",
        value
    ):

        url = (
            "https://"
            + value
        )

        if not is_media(
            url
        ):

            return url

    return ""


# =========================================================
# MERGE DE CANDIDATOS
# =========================================================

def key_for(item):

    host = domain(
        item.get(
            "website",
            ""
        )
    )

    if host:

        return host

    return norm(
        item.get(
            "name",
            ""
        )
    )


def merge(
    pool,
    item
):

    name = clean(
        item.get(
            "name",
            ""
        )
    )

    if not name:

        return

    key = key_for(
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

    current = pool[
        key
    ]

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

    rank = {
        "RUMOR": 0,
        "ANNOUNCED": 1,
        "TESTNET": 2,
        "COMING SOON": 3,
        "NEW": 4,
        "LIVE": 5
    }

    old_status = current.get(
        "status",
        "RUMOR"
    )

    new_status = item.get(
        "status",
        "RUMOR"
    )

    if (
        rank.get(
            new_status,
            0
        )
        >
        rank.get(
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
            not current.get(
                field
            )
            and item.get(
                field
            )
        ):

            current[field] = (
                item[field]
            )

    old_date = clean(
        current.get(
            "firstSeen",
            ""
        )
    )

    new_date = clean(
        item.get(
            "firstSeen",
            ""
        )
    )

    if (
        new_date
        and (
            not old_date
            or new_date < old_date
        )
    ):

        current["firstSeen"] = (
            new_date
        )


# =========================================================
# LIMPIAR BASE ANTERIOR
# =========================================================

def preserve_existing(item):

    name_key = norm(
        item.get(
            "name",
            ""
        )
    )

    if name_key in PINNED_KNOWN:

        return True

    if item.get(
        "pinned"
    ) is True:

        return True

    if "manual" in clean(
        item.get(
            "detectedBy",
            ""
        )
    ).lower():

        return True

    return (
        int(
            item.get(
                "scannerVersion",
                0
            )
            or 0
        )
        >= SCANNER_VERSION
    )


def load_database():

    database = load_json(
        DB_FILE,
        {
            "updatedAt": TODAY,
            "launchpads": []
        }
    )

    pool = {}

    for item in database.get(
        "launchpads",
        []
    ):

        if not isinstance(
            item,
            dict
        ):

            continue

        # Borra automáticamente registros
        # malos creados por scanner v1.

        if not preserve_existing(
            item
        ):

            continue

        name_key = norm(
            item.get(
                "name",
                ""
            )
        )

        if is_media(
            item.get(
                "website",
                ""
            )
        ):

            continue

        if (
            name_key in KNOWN_LAUNCHPADS
            and name_key not in PINNED_KNOWN
        ):

            continue

        clone = dict(
            item
        )

        clone["_sources"] = [
            source.strip()
            for source in clean(
                item.get(
                    "detectedBy",
                    "Manual"
                )
            ).split(
                "+"
            )
            if source.strip()
        ]

        clone["_publishers"] = []

        merge(
            pool,
            clone
        )

    return pool


# =========================================================
# GOOGLE NEWS SCANNER
# =========================================================

def scan_news(
    pool,
    state
):

    log(
        "Scanning Google News..."
    )

    queries = (
        '"memecoin launchpad" when:3d',
        '"token launchpad" crypto when:3d',
        '"bonding curve" memecoin platform when:3d',
        '"fair launch" crypto platform when:3d',
        '"launching" "memecoin launchpad" when:3d'
    )

    seen = set(
        state.get(
            "news_seen",
            []
        )
    )

    grouped = {}

    for query in queries:

        params = urllib.parse.urlencode(
            {
                "q": query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en"
            }
        )

        url = (
            "https://news.google.com/"
            "rss/search?"
            + params
        )

        xml = safe_text(
            url,
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
        )[:30]:

            raw_title = clean(
                article.findtext(
                    "title"
                )
            )

            # IMPORTANTE:
            # elimina HOKANEWS.COM,
            # Crypto Briefing, etc.
            title = strip_publisher(
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

            identity = (
                link
                or raw_title
            )

            if identity:

                seen.add(
                    identity
                )

            if published:

                if (
                    NOW - published
                    >
                    timedelta(
                        days=4
                    )
                ):

                    continue

            if not is_launch_signal(
                title
            ):

                continue

            name = guess_news_name(
                title
            )

            if not name:

                continue

            name_key = norm(
                name
            )

            # Evita Pump.fun,
            # Pools, etc.

            if name_key in KNOWN_LAUNCHPADS:

                continue

            website = website_from_name(
                name
            )

            if (
                website
                and is_media(
                    website
                )
            ):

                continue

            key = (
                domain(
                    website
                )
                or name_key
            )

            if key not in grouped:

                grouped[key] = {
                    "name": name,
                    "website": website,
                    "titles": [],
                    "links": [],
                    "publishers": set(),
                    "dates": []
                }

            grouped[key][
                "titles"
            ].append(
                title
            )

            if link:

                grouped[key][
                    "links"
                ].append(
                    link
                )

            if publisher:

                grouped[key][
                    "publishers"
                ].add(
                    publisher
                )

            if published:

                grouped[key][
                    "dates"
                ].append(
                    published
                )

    # =====================================================
    # CONFIRMAR NOTICIA
    # =====================================================

    for group in grouped.values():

        publishers = sorted(
            group[
                "publishers"
            ]
        )

        website = group[
            "website"
        ]

        # Si no tenemos dominio oficial,
        # exigimos al menos 2 medios distintos.

        if (
            not website
            and len(
                publishers
            ) < 2
        ):

            continue

        combined = " ".join(
            group[
                "titles"
            ]
        )

        published = (
            min(
                group[
                    "dates"
                ]
            )
            if group[
                "dates"
            ]
            else None
        )

        if website:

            links = inspect_site(
                website,
                combined
            )

        else:

            links = {
                "website": "",
                "x": "",
                "discord": "",
                "github": ""
            }

        candidate = {
            "name": group[
                "name"
            ],
            "status": status_from_text(
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
            "description": group[
                "titles"
            ][0][:320],
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
                group[
                    "links"
                ][0]
                if group[
                    "links"
                ]
                else ""
            ),
            "_sources": [
                "News"
            ],
            "_publishers": (
                publishers
            )
        }

        merge(
            pool,
            candidate
        )

    state[
        "news_seen"
    ] = list(
        seen
    )[-2000:]


# =========================================================
# GITHUB SCANNER
# =========================================================

def scan_github(
    pool,
    state
):

    log(
        "Scanning GitHub..."
    )

    since = (
        NOW
        - timedelta(
            days=5
        )
    ).date().isoformat()

    queries = (
        f'"memecoin launchpad" '
        f'in:name,description,readme '
        f'pushed:>={since}',

        f'"token launchpad" '
        f'in:name,description,readme '
        f'pushed:>={since}',

        f'"bonding curve" memecoin '
        f'in:name,description,readme '
        f'pushed:>={since}',

        f'"fair launch" token platform '
        f'in:name,description,readme '
        f'pushed:>={since}'
    )

    seen = set(
        state.get(
            "github_seen",
            []
        )
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
                    "per_page": 12
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

            # Evita tutoriales,
            # demos y plantillas.

            if any(
                bad in repo_name.lower()
                for bad in (
                    "tutorial",
                    "example",
                    "template",
                    "demo",
                    "course",
                    "homework"
                )
            ):

                continue

            # Leer README.

            readme_url = (
                "https://api.github.com/"
                "repos/"
                + urllib.parse.quote(
                    full_name,
                    safe="/"
                )
                + "/readme"
            )

            readme = safe_json(
                readme_url,
                25
            )

            readme_text = ""

            if (
                isinstance(
                    readme,
                    dict
                )
                and readme.get(
                    "content"
                )
            ):

                try:

                    readme_text = (
                        base64.b64decode(
                            readme[
                                "content"
                            ]
                        ).decode(
                            "utf-8",
                            errors="replace"
                        )
                    )

                except Exception:

                    pass

            combined = (
                repo_name
                + " "
                + description
                + " "
                + homepage
                + "\n"
                + readme_text[
                    :250000
                ]
            )

            if not is_launch_signal(
                combined
            ):

                continue

            links = inspect_site(
                homepage,
                combined
            )

            if homepage.startswith(
                (
                    "http://",
                    "https://"
                )
            ):

                website = homepage

            else:

                website = links.get(
                    "website",
                    ""
                )

            if (
                website
                and is_media(
                    website
                )
            ):

                continue

            # Un repo solo NO basta.
            # Debe tener web, X o Discord.

            if (
                not website
                and not links.get(
                    "x"
                )
                and not links.get(
                    "discord"
                )
            ):

                continue

            if website:

                name = name_from_domain(
                    website
                )

            else:

                name = repo_name.replace(
                    "-",
                    " "
                ).replace(
                    "_",
                    " "
                ).title()

            if not name:

                continue

            if norm(
                name
            ) in KNOWN_LAUNCHPADS:

                continue

            created = parse_date(
                repo.get(
                    "created_at"
                )
            )

            candidate = {
                "name": name,
                "status": status_from_text(
                    combined,
                    created
                ),
                "chain": detect_chain(
                    combined
                ),
                "firstSeen": (
                    created.date().isoformat()
                    if created
                    else TODAY
                ),
                "confidence": 0,
                "description": (
                    description[
                        :320
                    ]
                    or
                    "Recent GitHub project matching launchpad signals."
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
                "github": github_url,
                "source": github_url,
                "_sources": [
                    "GitHub"
                ],
                "_publishers": []
            }

            merge(
                pool,
                candidate
            )

    state[
        "github_seen"
    ] = list(
        seen
    )[-2500:]


# =========================================================
# DEFILLAMA
# =========================================================

def scan_defillama(
    pool,
    state
):

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
            protocol.get(
                "id"
            )
            or protocol.get(
                "slug"
            )
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

    # Primera ejecución:
    # crear base conocida.

    if not old_seen:

        state[
            "defillama_seen"
        ] = sorted(
            current_ids
        )

        log(
            "DefiLlama baseline created: "
            + str(
                len(
                    current_ids
                )
            )
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

        if not name:

            continue

        if norm(
            name
        ) in KNOWN_LAUNCHPADS:

            continue

        website = clean(
            protocol.get(
                "url"
            )
        )

        if (
            website
            and is_media(
                website
            )
        ):

            continue

        description = clean(
            protocol.get(
                "description"
            )
        )

        links = inspect_site(
            website,
            description
        )

        twitter = clean(
            protocol.get(
                "twitter"
            )
        )

        if (
            twitter
            and not twitter.startswith(
                "http"
            )
        ):

            twitter = (
                "https://x.com/"
                + twitter.lstrip(
                    "@"
                )
            )

        if (
            twitter
            and not links.get(
                "x"
            )
        ):

            links[
                "x"
            ] = twitter

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
                str(
                    item
                )
                for item in chains[
                    :4
                ]
            )

        else:

            chain = clean(
                chains
            )

        slug = str(
            protocol.get(
                "slug"
            )
            or name
        )

        candidate = {
            "name": name,
            "status": "NEW",
            "chain": chain,
            "firstSeen": TODAY,
            "confidence": 0,
            "description": (
                description[
                    :320
                ]
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
                "https://defillama.com/"
                "protocol/"
                + urllib.parse.quote(
                    slug
                )
            ),
            "_sources": [
                "DefiLlama"
            ],
            "_publishers": []
        }

        merge(
            pool,
            candidate
        )

    state[
        "defillama_seen"
    ] = sorted(
        current_ids
    )


# =========================================================
# DEX SCREENER
# =========================================================

def dex_profile_links(
    profile
):

    result = {
        "website": "",
        "x": "",
        "discord": "",
        "github": ""
    }

    for item in (
        profile.get(
            "links"
        )
        or []
    ):

        if not isinstance(
            item,
            dict
        ):

            continue

        url = clean(
            item.get(
                "url"
            )
        )

        label = clean(
            item.get(
                "label"
            )
        ).lower()

        link_type = clean(
            item.get(
                "type"
            )
        ).lower()

        host = domain(
            url
        )

        low = url.lower()

        if not host:

            continue

        if host in {
            "x.com",
            "twitter.com"
        }:

            if not result[
                "x"
            ]:

                result[
                    "x"
                ] = url

        elif (
            host == "discord.gg"
            or (
                host == "discord.com"
                and "/invite/" in low
            )
        ):

            if not result[
                "discord"
            ]:

                result[
                    "discord"
                ] = url

        elif host == "github.com":

            if not result[
                "github"
            ]:

                result[
                    "github"
                ] = url

        elif not is_media(
            url
        ):

            if (
                "website" in label
                or "website" in link_type
                or not result[
                    "website"
                ]
            ):

                if not result[
                    "website"
                ]:

                    result[
                        "website"
                    ] = url

    return result


def scan_dexscreener(
    pool,
    state
):

    log(
        "Scanning DEX Screener..."
    )

    data = safe_json(
        "https://api.dexscreener.com/"
        "token-profiles/latest/v1",
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

    all_seen = set(
        old_seen
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

    # Primera ejecución = baseline.

    if not old_seen:

        state[
            "dex_profiles_seen"
        ] = sorted(
            current
        )

        log(
            "DEX Screener baseline created: "
            + str(
                len(
                    current
                )
            )
        )

        return

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

        links = dex_profile_links(
            profile
        )

        website = links.get(
            "website",
            ""
        )

        if not website:

            continue

        if is_media(
            website
        ):

            continue

        # IMPORTANTE:
        # No basta con que el token diga
        # "launchpad".
        # La web debe confirmar que realmente
        # es una plataforma de lanzamiento.

        page = safe_text(
            website,
            12
        )

        combined = (
            description
            + "\n"
            + page[
                :500000
            ]
        )

        if not is_launch_signal(
            combined
        ):

            continue

        name = name_from_domain(
            website
        )

        if not name:

            continue

        if norm(
            name
        ) in KNOWN_LAUNCHPADS:

            continue

        page_links = public_links(
            page
        )

        for key in (
            "x",
            "discord",
            "github"
        ):

            if (
                not links[
                    key
                ]
                and page_links[
                    key
                ]
            ):

                links[
                    key
                ] = page_links[
                    key
                ]

        candidate = {
            "name": name,
            "status": status_from_text(
                combined,
                NOW
            ),
            "chain": (
                chain
                or detect_chain(
                    combined
                )
            ),
            "firstSeen": TODAY,
            "confidence": 0,
            "description": (
                description[
                    :320
                ]
                or
                "New DEX Screener profile linked to a launchpad website."
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
            ],
            "_publishers": []
        }

        merge(
            pool,
            candidate
        )

    state[
        "dex_profiles_seen"
    ] = list(
        all_seen
    )[-3000:]


# =========================================================
# CONFIANZA
# =========================================================

def calculate_confidence(
    item
):

    name_key = norm(
        item.get(
            "name",
            ""
        )
    )

    if name_key in PINNED_KNOWN:

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

    score = 20

    if "News" in sources:

        score += 20

        score += min(
            20,
            max(
                0,
                len(
                    publishers
                ) - 1
            )
            * 10
        )

    if "GitHub" in sources:

        score += 28

    if "DefiLlama" in sources:

        score += 55

    if "DEX Screener" in sources:

        score += 30

    if len(
        sources
    ) > 1:

        score += min(
            20,
            (
                len(
                    sources
                )
                - 1
            )
            * 10
        )

    if item.get(
        "website"
    ):

        score += 10

    if item.get(
        "x"
    ):

        score += 5

    if item.get(
        "discord"
    ):

        score += 5

    if item.get(
        "github"
    ):

        score += 5

    if item.get(
        "status"
    ) in {
        "ANNOUNCED",
        "COMING SOON",
        "TESTNET"
    }:

        score += 8

    return min(
        100,
        max(
            1,
            score
        )
    )


# =========================================================
# RESULTADO FINAL
# =========================================================

def finalize(
    pool
):

    results = []

    for item in pool.values():

        name = clean(
            item.get(
                "name",
                ""
            )
        )

        name_key = norm(
            name
        )

        if not name_key:

            continue

        if is_media(
            item.get(
                "website",
                ""
            )
        ):

            continue

        # Launchpads antiguas no aparecen
        # como descubrimientos.

        if (
            name_key in KNOWN_LAUNCHPADS
            and name_key not in PINNED_KNOWN
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

        detected_labels = []

        for source in sources:

            if (
                source == "News"
                and publishers
            ):

                detected_labels.append(
                    "News ("
                    + str(
                        len(
                            publishers
                        )
                    )
                    + " publishers)"
                )

            else:

                detected_labels.append(
                    source
                )

        if detected_labels:

            item[
                "detectedBy"
            ] = " + ".join(
                detected_labels
            )

        old_confidence = int(
            item.get(
                "confidence",
                0
            )
            or 0
        )

        new_confidence = (
            calculate_confidence(
                item
            )
        )

        item[
            "confidence"
        ] = max(
            old_confidence,
            new_confidence
        )

        item[
            "scannerVersion"
        ] = SCANNER_VERSION

        # Eliminar ruido débil.
        # Pools.trade queda porque está PINNED.

        if (
            name_key not in PINNED_KNOWN
            and item[
                "confidence"
            ] < 60
        ):

            continue

        item.pop(
            "_sources",
            None
        )

        item.pop(
            "_publishers",
            None
        )

        fields = (
            "chain",
            "firstSeen",
            "description",
            "website",
            "x",
            "discord",
            "github",
            "source"
        )

        for field in fields:

            item[
                field
            ] = clean(
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
# MAIN
# =========================================================

def main():

    log(
        "Starting Launchpad Intelligence Scanner v2..."
    )

    pool = load_database()

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
        )
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
        "launchpads": launchpads
    }

    save_json(
        DB_FILE,
        database
    )

    state[
        "last_run"
    ] = updated

    state[
        "scanner_version"
    ] = SCANNER_VERSION

    save_json(
        STATE_FILE,
        state
    )

    log(
        "Finished. "
        + str(
            len(
                launchpads
            )
        )
        + " verified launchpad record(s)."
    )


if __name__ == "__main__":

    main()
