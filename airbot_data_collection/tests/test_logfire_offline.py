import logfire
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


# 本地文件导出器（也可用 ConsoleSpanExporter 写 jsonl）
exporter = InMemorySpanExporter()  # 也可以用 FileSpanExporter
logfire.configure(
    send_to_logfire=False,
    additional_span_processors=[SimpleSpanProcessor(exporter)],
)

# 3. 写数据
parts = [
    {"cpu": 12.3, "mem": 4.5},
    {"disk": 7.8, "net": 1.2},
]
for p in parts:
    logfire.info("part_update", **p)

# 4. 导出到本地文件
import json, pathlib, datetime, gzip, os

out_dir = pathlib.Path(".logfire/logfire_offline")
out_dir.mkdir(exist_ok=True)

fname = out_dir / f"spans-{datetime.datetime.now().isoformat()}.jsonl.gz"
with gzip.open(fname, "wt", encoding="utf-8") as f:
    for span in exporter.get_finished_spans():
        f.write(json.dumps(span.to_json()) + "\n")

# 5. 把目录 logfire_offline/ 整个拷走（U 盘、rsync 均可）
print("Offline spans written to", os.path.abspath(fname))
