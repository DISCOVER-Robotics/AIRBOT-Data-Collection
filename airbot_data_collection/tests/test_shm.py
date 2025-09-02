import numpy as np
import multiprocessing as mp
from multiprocessing import shared_memory


def worker(shm_name, shape, dtype):
    """
    子进程函数，连接到共享内存，并修改 NumPy 数组。
    """
    # 1. 连接到已有的共享内存块
    existing_shm = shared_memory.SharedMemory(name=shm_name)

    # 2. 从共享内存创建一个 NumPy 数组视图
    # 'buffer=existing_shm.buf' 指向共享内存的缓冲区
    np_array = np.ndarray(shape, dtype=dtype, buffer=existing_shm.buf)

    print(f"子进程开始: 数组的第一个元素是 {np_array[0]}")

    # 3. 修改数组
    np_array[:] = np_array[:] * 2

    print(f"子进程结束: 数组的第一个元素被修改为 {np_array[0]}")

    # 4. 子进程不需要释放共享内存，只需要关闭其连接
    existing_shm.close()


if __name__ == "__main__":
    # 原始的 NumPy 数组
    my_array = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)

    # 1. 创建共享内存块，大小为数组的字节数
    # create=True 表示如果同名共享内存不存在则创建它
    shm = shared_memory.SharedMemory(create=True, size=my_array.nbytes)

    # 2. 从共享内存创建一个 NumPy 数组视图
    shm_array = np.ndarray(my_array.shape, dtype=my_array.dtype, buffer=shm.buf)

    # 3. 将数据复制到共享内存中
    shm_array[:] = my_array[:]

    print(f"主进程开始: 数组的原始值是 {my_array}")

    # 4. 启动子进程，并将共享内存的名称、形状和数据类型作为参数传递
    p = mp.Process(target=worker, args=(shm.name, my_array.shape, my_array.dtype))
    p.start()
    p.join()

    # 5. 子进程修改后，主进程中的 shm_array 也随之改变
    print(f"主进程结束: 数组的新值是 {shm_array}")

    # 6. 最后，主进程负责解除链接和释放共享内存
    shm.close()
    shm.unlink()
