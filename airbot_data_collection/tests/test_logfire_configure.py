import logfire


logfire.configure(
    # send_to_logfire="if-token-present",
    send_to_logfire=None,
    token=None,
    console=logfire.ConsoleOptions(min_log_level="info"),
    config_dir="..",
    data_dir=".logfire",
    min_level="info",
)

with logfire.span("root") as root:
    root.set_level("debug")  # 事后设置，不影响过滤
    with logfire.span("debug span excluded", _level="debug"):
        logfire.info("info message")
