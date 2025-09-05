import logfire

logfire.configure()

histogram = logfire.metric_histogram(
    "request_duration", unit="ms", description="Duration of requests"
)

for duration in [10, 20, 30, 40, 50]:
    histogram.record(duration)


# import logfire

# logfire.configure()

# logfire.instrument_system_metrics()
