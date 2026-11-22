from .contracts import Catalog, CatalogEntry

DATASET_ID = "synthetic-v1"
RULES_VERSION = "demo-v1"
CATALOG = Catalog(
    datasets=(CatalogEntry(id=DATASET_ID, name="人工样例 · 4 个交易日"),),
    baselines=(
        CatalogEntry(id="cash", name="维持空仓"),
        CatalogEntry(id="factor-rank", name="因子排序 · 单股半仓"),
    ),
)
