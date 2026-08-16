# -*- coding: utf-8 -*-
"""backend 包。

配置收敛后，本包不再加载 JSON 配置（data/config.json）。所有配置统一由
backend/config.yaml 承载（见 app.py / enhanced_routes.py / main.py）。
子模块（db / qa_engine / app 等）按需直接导入。
"""
