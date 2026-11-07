# Databricks notebook source
# MAGIC %md
# MAGIC # Seed `hackcamp.agent.eval_labels` (30–50 repos)
# MAGIC Labels only for repos already in `hackcamp.silver.repos` / gold corpus.

# COMMAND ----------

from pyspark.sql import Row
from pyspark.sql.types import StringType, StructField, StructType

# label ∈ {at_risk, ignored, healthy, hard_case}
# ignored = officially deprecated (park; no future PR-review attention)
# hard_case = mature/quiet-but-fine OR recently revived / ambiguous formula cases
LABELS = [
    # --- ignored (deprecated / archived-as-deprecated) ---
    Row(
        "request/request",
        "ignored",
        "https://github.com/request/request/issues/3142",
        "Officially deprecated/archived; maintainers directed users elsewhere — park, do not re-triage.",
    ),
    Row(
        "moment/moment",
        "ignored",
        "https://momentjs.com/docs/#/-project-status/",
        "Project status: legacy; Moment team recommends alternatives — ignored for ongoing review.",
    ),
    Row(
        "dgrijalva/jwt-go",
        "ignored",
        "https://github.com/dgrijalva/jwt-go",
        "Archived GitHub repo; community moved to golang-jwt/jwt.",
    ),
    Row(
        "gorilla/mux",
        "ignored",
        "https://github.com/gorilla/mux/issues/714",
        "Gorilla toolkit archived/unmaintained; no future maintainer PR reviews.",
    ),
    Row(
        "codehaus/jackson",
        "ignored",
        "https://github.com/codehaus/jackson",
        "Legacy Codehaus Jackson line; superseded by FasterXML/jackson.",
    ),
    # --- at_risk (still living remediation; not officially parked) ---
    Row(
        "kennethreitz/records",
        "at_risk",
        "https://github.com/kennethreitz/records",
        "Long release gap / minimal maintenance signals for a once-popular helper.",
    ),
    # --- healthy ---
    Row(
        "psf/requests",
        "healthy",
        "https://github.com/psf/requests/releases",
        "Well-known; recent releases and active PSF maintenance.",
    ),
    Row(
        "pallets/flask",
        "healthy",
        "https://github.com/pallets/flask/releases",
        "Active Pallets release train and multiple maintainers.",
    ),
    Row(
        "encode/httpx",
        "healthy",
        "https://github.com/encode/httpx/releases",
        "Recent releases; Encode project actively maintained.",
    ),
    Row(
        "tiangolo/fastapi",
        "healthy",
        "https://github.com/tiangolo/fastapi/releases",
        "High activity, frequent releases, broad maintainer/contributor base.",
    ),
    Row(
        "joke2k/faker",
        "healthy",
        "https://github.com/joke2k/faker/releases",
        "Regular releases and ongoing community maintenance.",
    ),
    Row(
        "pydata/xarray",
        "healthy",
        "https://github.com/pydata/xarray/releases",
        "Active scientific Python project with recent releases.",
    ),
    Row(
        "facebook/react",
        "healthy",
        "https://github.com/facebook/react/releases",
        "Meta-maintained; frequent releases and many active maintainers.",
    ),
    Row(
        "vercel/next.js",
        "healthy",
        "https://github.com/vercel/next.js/releases",
        "Very active release cadence under Vercel maintainership.",
    ),
    Row(
        "axios/axios",
        "healthy",
        "https://github.com/axios/axios/releases",
        "Recent releases and ongoing maintenance.",
    ),
    Row(
        "mrdoob/three.js",
        "healthy",
        "https://github.com/mrdoob/three.js/releases",
        "Continuous releases; well-known active graphics library.",
    ),
    Row(
        "golang/go",
        "healthy",
        "https://github.com/golang/go/releases",
        "Go language repo; sustained release and maintainer activity.",
    ),
    Row(
        "gin-gonic/gin",
        "healthy",
        "https://github.com/gin-gonic/gin/releases",
        "Popular Go web framework with ongoing releases.",
    ),
    Row(
        "spf13/cobra",
        "healthy",
        "https://github.com/spf13/cobra/releases",
        "Widely used; active maintainers and recent releases.",
    ),
    Row(
        "labstack/echo",
        "healthy",
        "https://github.com/labstack/echo/releases",
        "Active Go framework with recent releases.",
    ),
    Row(
        "go-chi/chi",
        "healthy",
        "https://github.com/go-chi/chi/releases",
        "Healthy router project with ongoing maintenance.",
    ),
    Row(
        "hashicorp/terraform",
        "healthy",
        "https://github.com/hashicorp/terraform/releases",
        "HashiCorp-maintained; frequent releases.",
    ),
    Row(
        "rust-lang/rust",
        "healthy",
        "https://github.com/rust-lang/rust/releases",
        "Rust language; continuous release train and many maintainers.",
    ),
    Row(
        "tokio-rs/tokio",
        "healthy",
        "https://github.com/tokio-rs/tokio/releases",
        "Core async runtime; active Tokio org maintainers.",
    ),
    Row(
        "serde-rs/serde",
        "healthy",
        "https://github.com/serde-rs/serde/releases",
        "Foundational crate with ongoing releases.",
    ),
    Row(
        "clap-rs/clap",
        "healthy",
        "https://github.com/clap-rs/clap/releases",
        "Active CLI crate with recent releases.",
    ),
    Row(
        "sharkdp/fd",
        "healthy",
        "https://github.com/sharkdp/fd/releases",
        "Actively maintained CLI tool with recent releases.",
    ),
    Row(
        "hyperium/hyper",
        "healthy",
        "https://github.com/hyperium/hyper/releases",
        "Core HTTP stack; ongoing Hyperium maintenance.",
    ),
    Row(
        "rust-lang/cargo",
        "healthy",
        "https://github.com/rust-lang/cargo/releases",
        "Official Cargo; sustained maintenance.",
    ),
    Row(
        "spring-projects/spring-boot",
        "healthy",
        "https://github.com/spring-projects/spring-boot/releases",
        "Spring team releases; many active maintainers.",
    ),
    Row(
        "apache/kafka",
        "healthy",
        "https://github.com/apache/kafka/releases",
        "Apache project with ongoing releases.",
    ),
    Row(
        "elastic/elasticsearch",
        "healthy",
        "https://github.com/elastic/elasticsearch/releases",
        "Elastic-maintained; frequent releases.",
    ),
    Row(
        "google/guava",
        "healthy",
        "https://github.com/google/guava/releases",
        "Google-maintained; continued releases.",
    ),
    Row(
        "junit-team/junit5",
        "healthy",
        "https://github.com/junit-team/junit5/releases",
        "Active JUnit team releases.",
    ),
    Row(
        "FasterXML/jackson-databind",
        "healthy",
        "https://github.com/FasterXML/jackson-databind/releases",
        "FasterXML Jackson line; ongoing releases.",
    ),
    Row(
        "netty/netty",
        "healthy",
        "https://github.com/netty/netty/releases",
        "Active Netty project releases.",
    ),
    Row(
        "square/okhttp",
        "healthy",
        "https://github.com/square/okhttp/releases",
        "Square-maintained; recent releases.",
    ),
    # --- hard_case: quiet/mature but fine ---
    Row(
        "vuejs/vue",
        "hard_case",
        "https://github.com/vuejs/vue",
        "Vue 2 line is mature/maintenance-mode while Vue 3 lives elsewhere — quiet but not abandoned in the formula sense.",
    ),
    Row(
        "expressjs/express",
        "hard_case",
        "https://github.com/expressjs/express",
        "Mature framework; slower cadence can look risky but project remains healthy.",
    ),
    Row(
        "lodash/lodash",
        "hard_case",
        "https://github.com/lodash/lodash",
        "Largely 'done' utility library; low commit volume is expected.",
    ),
    Row(
        "jquery/jquery",
        "hard_case",
        "https://github.com/jquery/jquery",
        "Mature/stable; quieter activity than peak years but still maintained.",
    ),
    Row(
        "BurntSushi/ripgrep",
        "hard_case",
        "https://github.com/BurntSushi/ripgrep",
        "High-quality mature CLI; release gaps are normal for a stable tool.",
    ),
    # --- hard_case: watchlist / ambiguous ---
    Row(
        "python-poetry/poetry",
        "hard_case",
        "https://github.com/python-poetry/poetry",
        "Important tooling with uneven velocity — easy false alarm for at-risk.",
    ),
    Row(
        "aio-libs/aiohttp",
        "hard_case",
        "https://github.com/aio-libs/aiohttp",
        "Core async HTTP stack; formula may flag watchlist despite ongoing care.",
    ),
    Row(
        "scrapy/scrapy",
        "hard_case",
        "https://github.com/scrapy/scrapy",
        "Long-lived project; slower periods shouldn't auto-mean dying.",
    ),
    Row(
        "sirupsen/logrus",
        "hard_case",
        "https://github.com/sirupsen/logrus",
        "Maintenance-mode logging library still widely used; ambiguous risk.",
    ),
    Row(
        "urfave/cli",
        "hard_case",
        "https://github.com/urfave/cli",
        "v1 vs v2 transition history makes activity signals noisy.",
    ),
    Row(
        "actix/actix-web",
        "hard_case",
        "https://github.com/actix/actix-web",
        "Past maintainer turbulence then recovery — hard case for risk models.",
    ),
    Row(
        "diesel-rs/diesel",
        "hard_case",
        "https://github.com/diesel-rs/diesel",
        "Solid ORM with bursty release cadence; easy to mis-label.",
    ),
    Row(
        "hibernate/hibernate-orm",
        "hard_case",
        "https://github.com/hibernate/hibernate-orm",
        "Enterprise ORM; quieter windows are common for a mature stack.",
    ),
]

schema = StructType(
    [
        StructField("repo_id", StringType(), False),
        StructField("label", StringType(), False),
        StructField("label_source", StringType(), True),
        StructField("notes", StringType(), True),
    ]
)

labels_df = spark.createDataFrame(LABELS, schema=schema)
print(f"Prepared {labels_df.count()} label rows")

# COMMAND ----------

corpus = spark.table("hackcamp.silver.repos").select("repo_id").distinct()
missing = labels_df.join(corpus, on="repo_id", how="left_anti")
missing_count = missing.count()
if missing_count:
    display(missing)
    raise RuntimeError(f"{missing_count} labelled repos are not in the corpus")

# Replace table contents for a clean labelled set
spark.sql("DELETE FROM hackcamp.agent.eval_labels")
labels_df.write.mode("append").saveAsTable("hackcamp.agent.eval_labels")

summary = (
    spark.table("hackcamp.agent.eval_labels")
    .groupBy("label")
    .count()
    .orderBy("label")
)
print("eval_labels by class:")
display(summary)
total = spark.table("hackcamp.agent.eval_labels").count()
print(f"TOTAL_EVAL_LABELS={total}")
assert 30 <= total <= 50, total
print("EVAL_LABELS_SEED_OK")
