"""核心逻辑。

与 main.py 的参数解析解耦，方便单元测试。
接单时把真正的业务逻辑写进 run()。
"""
from pathlib import Path


def run(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    """TODO: 实现真正的业务逻辑。

    参数：
        input_path: 输入路径
        output_path: 输出目录
        verbose: 是否打印详细过程
    """
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    output_path.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"输入: {input_path}")
        print(f"输出: {output_path}")

    # TODO: 在这里写真正的处理逻辑
    # 例如：遍历 input_path 下的文件，处理后写入 output_path
    files = (
        [p for p in input_path.iterdir() if p.is_file()]
        if input_path.is_dir()
        else [input_path]
    )
    if verbose:
        print(f"待处理文件数: {len(files)}")
    # for f in files:
    #     ... 处理 ...
