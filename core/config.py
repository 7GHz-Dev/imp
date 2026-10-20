# -*- coding: utf-8 -*-
"""อ่าน config.ini (ถ้าไม่มีใช้ config.example.ini) — path ทั้งหมดคิดจากโฟลเดอร์โปรแกรม"""
import configparser
import os
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class NetbaySettings:
    url: str
    username: str
    password: str
    declaration_type: str
    importer_search: str
    importer_name: str
    vessel: str
    voyage: str
    origin_country: str
    release_port: str
    headless: bool


@dataclass
class ErpSettings:
    """ERP-KOLA ที่ worker.py ไปรับงาน Draft ใบขน"""
    url: str
    api_key: str
    worker_name: str
    poll_seconds: int


@dataclass
class Settings:
    db_path: str
    output_dir: str
    work_dir: str
    csv_template: str
    brand_country: str
    tariff_file: str
    csv_encoding: str
    excel_method: str
    host: str
    port: int
    netbay: NetbaySettings
    erp: ErpSettings = None


def load(path=None):
    if path is None:
        path = os.path.join(ROOT, 'config.ini')
        if not os.path.isfile(path):
            path = os.path.join(ROOT, 'config.example.ini')
    cfg = configparser.ConfigParser()
    with open(path, encoding='utf-8') as f:
        cfg.read_file(f)
    p = lambda sec, key: os.path.join(ROOT, cfg.get(sec, key))
    nb = cfg['netbay']
    return Settings(
        db_path=p('database', 'path'),
        output_dir=p('paths', 'output_dir'),
        work_dir=p('paths', 'work_dir'),
        csv_template=p('paths', 'csv_template'),
        brand_country=p('paths', 'brand_country'),
        tariff_file=p('paths', 'tariff_file'),
        csv_encoding=cfg.get('csv', 'encoding', fallback='tis-620'),
        excel_method=cfg.get('excel', 'method', fallback='auto'),
        host=cfg.get('web', 'host', fallback='127.0.0.1'),
        port=cfg.getint('web', 'port', fallback=5000),
        netbay=NetbaySettings(
            url=nb.get('url', ''),
            username=nb.get('username', ''),
            password=nb.get('password', ''),
            declaration_type=nb.get('declaration_type', '610'),
            importer_search=nb.get('importer_search', 'MAESOT FREE ZONE'),
            importer_name=nb.get('importer_name', ''),
            vessel=nb.get('vessel', ''),
            voyage=nb.get('voyage', 'XXXX'),
            origin_country=nb.get('origin_country', 'JP'),
            release_port=nb.get('release_port', ''),
            headless=nb.getboolean('headless', fallback=False),
        ),
        erp=ErpSettings(
            url=cfg.get('erp', 'url', fallback='https://erp-kola.vercel.app').rstrip('/'),
            api_key=cfg.get('erp', 'api_key', fallback=''),
            worker_name=cfg.get('erp', 'worker_name', fallback=''),
            poll_seconds=cfg.getint('erp', 'poll_seconds', fallback=20),
        ),
    )
