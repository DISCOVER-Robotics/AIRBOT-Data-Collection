# Modules

- 请严格遵循 airdc/docs/prompts/prepare.md 中的说明！
- 实现完成后，请在 airdc/tests/modules/<模块类别小写复数> 目录下编写相应的配置文件，然后将路径传入 airdc/tests/modules/test_<模块类别小写复数>.py 脚本进行测试，确保测试通过。

## Sampler

请参考 airdc/docs/develop/modules.md中Sampler一节，分析将 /home/ghz/Work/lerobot/src/lerobot/scripts/lerobot_record.py 中的数据记录功能改写为DataSampler的子类是否可行，如果不可行，请说明需要在当前框架中增加哪些功能以支持该需求。如果可行，请在 airdc/airdc/common/samplers 目录下创建 lerobot_sampler.py 文件并进行实现，并确保通过测试。
