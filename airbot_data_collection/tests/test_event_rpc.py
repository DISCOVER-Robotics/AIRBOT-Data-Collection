import multiprocessing
import time


def worker(req_event, rsp_event):
    while True:
        req_event.wait()
        req_event.clear()
        rsp_event.set()


def main(num_tests=10):
    req_event = multiprocessing.Event()
    rsp_event = multiprocessing.Event()
    p = multiprocessing.Process(target=worker, args=(req_event, rsp_event))
    p.start()

    for _ in range(num_tests):
        start = time.perf_counter()
        req_event.set()
        rsp_event.wait()
        print(f"{(time.perf_counter() - start) * 1000:.6f} ms")
        rsp_event.clear()
    p.join()


if __name__ == "__main__":
    main()
