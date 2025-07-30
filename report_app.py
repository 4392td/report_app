import streamlit as st
import pandas as pd
import openai
from datetime import datetime, timedelta, date
import json
import re
from typing import Dict, List, Tuple
import base64
from io import BytesIO
import numpy as np
import sqlite3
import pickle
from pathlib import Path
import hashlib # ハッシュ生成用にインポート
from dotenv import load_dotenv # 追加
from multi_device_support import (
    init_multi_device_session, 
    sync_field_update, 
    get_sync_updates, 
    show_active_devices,
    auto_refresh_data
)
import os # 追加
import pytz # 日本時間取得用に追加

# .envファイルをロード
import pathlib
script_dir = pathlib.Path(__file__).parent.absolute()
env_path = script_dir / '.env'
load_dotenv(dotenv_path=env_path)

# 環境変数の再読み込みを強制
import importlib
import sys
if 'dotenv' in sys.modules:
    importlib.reload(sys.modules['dotenv'])
load_dotenv(dotenv_path=env_path, override=True)

def get_japan_time():
    """日本時間の現在時刻を取得する"""
    jst = pytz.timezone('Asia/Tokyo')
    return datetime.now(jst)

# --- Streamlitアプリのスタイル設定 ---
# アプリ全体の背景を白、文字を黒に設定
st.markdown(
    """
    <style>
    body {
        background-color: white !important;
        color: black !important;
    }
    .stApp {
        background-color: white !important;
        color: black !important;
    }
    /* Streamlitウィジェットの見た目をさらに調整 */
    h1, h2, h3, h4, h5, h6, strong, p, div, span, label {
        color: black !important;
    }
    div[data-testid="stSidebar"] {
        background-color: #f0f0f0 !important; /* サイドバーの背景を少し薄いグレーに (好みで調整) */
        color: black !important;
    }
    .stTextInput label, .stTextArea label, .stSelectbox label {
        color: black !important;
    }
    textarea {
        background-color: white !important;
        color: black !important;
        border: 1px solid #ccc !important;
        border-radius: 5px !important;
        padding: 10px !important;
    }
    textarea[disabled] { /* 読み取り専用のテキストエリアのスタイル */
        background-color: #f9f9f9 !important;
        color: #555 !important;
        opacity: 0.8 !important;
    }
    input[type="text"] {
        background-color: white !important;
        color: black !important;
        border: 1px solid #ccc !important;
        border-radius: 5px !important;
        padding: 10px !important;
    }
    /* ボタンのスタイル */
    button {
        background-color: #007bff !important;
        color: white !important;
        border-radius: 5px !important;
        padding: 8px 15px !important;
        transition: background-color 0.2s !important;
        border: none !important;
    }
    button:hover {
        background-color: #0056b3 !important;
    }
    button[data-testid="stFormSubmitButton"] {
        background-color: #28a745 !important;
    }
    button[data-testid="stFormSubmitButton"]:hover {
        background-color: #218838 !important;
    }
    /* 成功メッセージの色 */
    div[data-testid="stAlert"] div[role="alert"].streamlit-success {
        background-color: #d4edda !important;
        color: #155724 !important;
        border-color: #c3e6cb !important;
    }
    /* 警告メッセージの色 */
    div[data-testid="stAlert"] div[role="alert"].streamlit-warning {
        background-color: #fff3cd !important;
        color: #856404 !important;
        border-color: #ffeeba !important;
    }
    /* エラーメッセージの色 */
    div[data-testid="stAlert"] div[role="alert"].streamlit-error {
        background-color: #f8d7da !important;
        color: #721c24 !important;
        border-color: #f5c6cb !important;
    }
    .css-1ht1j8x { /* メトリックの背景を白に */
        background-color: white !important;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075) !important;
        border: 1px solid #e0e0e0;
    }
    /* カレンダーの背景を白に設定 */
    .react-datepicker {
        background-color: white !important;
        color: black !important; /* テキスト色も黒に */
    }
    .react-datepicker__header {
        background-color: white !important;
        color: black !important;
    }
    .react-datepicker__month-container {
        background-color: white !important;
        color: black !important;
    }
    .react-datepicker__day-name, .react-datepicker__day, .react-datepicker__time-name {
        color: black !important;
    }
    .react-datepicker__current-month {
        color: black !important;
    }
    .react-datepicker__navigation--previous, .react-datepicker__navigation--next {
        color: black !important;
    }
    /* 選択された日付の背景色を赤、文字色を白に設定 */
    .react-datepicker__day--selected,
    .react-datepicker__day--range-start,
    .react-datepicker__day--range-end,
    .react-datepicker__day--in-range {
        background-color: #ff4b4b !important; /* Streamlitのデフォルト赤色に近づける */
        color: white !important;
    }
    /* ホバー時の日付の背景色 */
    .react-datepicker__day:hover {
        background-color: #e0e0e0 !important; /* ホバー時の背景色を薄いグレーに */
        color: black !important;
    }
    /* 選択できない日付（過去や未来でmin/max_value外）の文字色 */
    .react-datepicker__day--disabled {
        color: #ccc !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
# --- スタイル設定ここまで ---

# ページ設定
st.set_page_config(
    page_title="アパレル店舗週次レポート作成システム",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- データベース設定とヘルパー関数 ---
DB_PATH = 'apparel_reports.db' # データベースファイル名変更

class DBManager:
    """データベース接続と操作を管理するクラス"""
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        """データベース接続を確立し、Rowファクトリを設定します。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # カラム名でアクセスできるようにする
        return conn

    def _init_db(self):
        """データベースとテーブルを初期化します。指定された店舗名のみを登録します。"""
        conn = self._get_connection()
        with conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS stores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS weekly_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id INTEGER NOT NULL,
                    monday_date TEXT NOT NULL, --YYYY-MM-DD形式
                    
                    daily_reports_json TEXT,    -- 各曜日の動向と要因をJSON文字列で保存
                    topics TEXT,
                    impact_day TEXT,
                    quantitative_data TEXT,
                    
                    generated_report_json TEXT, -- AI生成レポート（動向、要因、質問）をJSONで保存
                    modified_report_json TEXT,  -- 修正後のレポート（動向、要因、修正理由など）をJSONで保存
                    
                    timestamp TEXT,             -- 作成/最終更新日時
                    FOREIGN KEY (store_id) REFERENCES stores(id),
                    UNIQUE(store_id, monday_date)
                );
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS learning_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    input_context_hash TEXT NOT NULL UNIQUE, -- 入力コンテキストのハッシュ値
                    original_output_json TEXT,
                    modified_output_json TEXT,
                    edit_reason TEXT,
                    usage_count INTEGER DEFAULT 1,
                    last_used TEXT
                )
            ''')
            
            # 指定された店舗名のみを挿入 (既に存在する場合はスキップ)
            for store_name in ['RAY', 'RSJ', 'ROS', 'RNG']:
                conn.execute("INSERT OR IGNORE INTO stores (name) VALUES (?)", (store_name,))
            conn.commit()
        conn.close()

    def get_store_id_by_name(self, store_name: str) -> int:
        """ストア名からIDを取得します。"""
        conn = self._get_connection()
        store_id = conn.execute('SELECT id FROM stores WHERE name = ?', (store_name,)).fetchone()['id']
        conn.close()
        return store_id

    def get_store_name_by_id(self, store_id: int) -> str:
        """ストアIDから名前を取得します。"""
        conn = self._get_connection()
        store_name = conn.execute('SELECT name FROM stores WHERE id = ?', (store_id,)).fetchone()['name']
        conn.close()
        return store_name
    
    def get_all_stores(self) -> List[Tuple[int, str]]:
        """全ての店舗のIDと名前を取得します。"""
        conn = self._get_connection()
        stores = conn.execute('SELECT id, name FROM stores ORDER BY name').fetchall()
        conn.close()
        return [(s['id'], s['name']) for s in stores]

    def save_weekly_data(self, store_id: int, monday_date_str: str, data: Dict, original_report: Dict, modified_report: Dict = None):
        """週次データをDBに保存または更新します。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        daily_reports_json = json.dumps(data['daily_reports'], ensure_ascii=False)
        generated_report_json = json.dumps(original_report, ensure_ascii=False)
        modified_report_json = json.dumps(modified_report, ensure_ascii=False) if modified_report else None
        
        cursor.execute(
            'SELECT id FROM weekly_reports WHERE store_id = ? AND monday_date = ?',
            (store_id, monday_date_str)
        )
        existing_record = cursor.fetchone()

        if existing_record:
            cursor.execute('''
                UPDATE weekly_reports SET
                   daily_reports_json = ?, topics = ?, impact_day = ?,
                   quantitative_data = ?, generated_report_json = ?,
                   modified_report_json = ?, timestamp = ?
                WHERE id = ?
            ''', (
                daily_reports_json,
                data.get('topics', ''),
                data.get('impact_day', ''),
                data.get('quantitative_data', ''),
                generated_report_json,
                modified_report_json,
                datetime.now().isoformat(),
                existing_record['id']
            ))
        else:
            cursor.execute('''
                INSERT INTO weekly_reports 
                (store_id, monday_date, daily_reports_json, topics, impact_day, 
                 quantitative_data, generated_report_json, modified_report_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                store_id,
                monday_date_str,
                daily_reports_json,
                data.get('topics', ''),
                data.get('impact_day', ''),
                data.get('quantitative_data', ''),
                generated_report_json,
                modified_report_json,
                datetime.now().isoformat()
            ))
        
        conn.commit()
        conn.close()
        return existing_record is not None

    def get_weekly_report(self, store_id: int, monday_date_str: str) -> Dict:
        """指定された週のレポートデータを取得します。"""
        conn = self._get_connection()
        report_row = conn.execute(
            'SELECT * FROM weekly_reports WHERE store_id = ? AND monday_date = ?',
            (store_id, monday_date_str)
        ).fetchone()
        conn.close()

        if report_row:
            report_data = dict(report_row) # Rowオブジェクトを辞書に変換
            try:
                report_data['daily_reports'] = json.loads(report_data['daily_reports_json']) if report_data['daily_reports_json'] else {}
            except (json.JSONDecodeError, TypeError) as e:
                print(f"日次レポートデータの解析に失敗しました: {str(e)}")
                report_data['daily_reports'] = {}
                
            try:
                report_data['generated_report'] = json.loads(report_data['generated_report_json']) if report_data['generated_report_json'] else {}
            except (json.JSONDecodeError, TypeError) as e:
                print(f"生成レポートデータの解析に失敗しました: {str(e)}")
                report_data['generated_report'] = {}
                
            try:
                report_data['modified_report'] = json.loads(report_data['modified_report_json']) if report_data['modified_report_json'] else None
            except (json.JSONDecodeError, TypeError) as e:
                print(f"修正レポートデータの解析に失敗しました: {str(e)}")
                report_data['modified_report'] = None
            
            del report_data['daily_reports_json']
            del report_data['generated_report_json']
            if 'modified_report_json' in report_data:
                del report_data['modified_report_json']

            return report_data
        return {}
    
    def get_all_weekly_reports(self, store_id: int = None) -> List[Dict]:
        """全ての週次レポート、または指定した店舗の週次レポートを取得します。"""
        conn = self._get_connection()
        if store_id:
            reports_rows = conn.execute(
                'SELECT id, store_id, monday_date, timestamp, generated_report_json, modified_report_json '
                'FROM weekly_reports WHERE store_id = ? ORDER BY monday_date DESC', (store_id,)
            ).fetchall()
        else:
            reports_rows = conn.execute(
                'SELECT id, store_id, monday_date, timestamp, generated_report_json, modified_report_json '
                'FROM weekly_reports ORDER BY monday_date DESC'
            ).fetchall()
        conn.close()

        reports = []
        for row in reports_rows:
            report_data = dict(row)
            report_data['store_name'] = self.get_store_name_by_id(report_data['store_id'])
            
            # 生成レポートと修正レポートの有無をフラグとして追加
            report_data['has_generated'] = report_data['generated_report_json'] is not None
            report_data['has_modified'] = report_data['modified_report_json'] is not None

            # JSON文字列は生データとして保持し、必要に応じてパースする
            reports.append(report_data)
        return reports

    def find_similar_cases(self, current_data: Dict) -> str:
        """類似ケースを検索し、LLMに渡すためのコンテキストを生成します。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT daily_reports_json, modified_report_json 
            FROM weekly_reports 
            WHERE modified_report_json IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 5
        ''') 
        
        results = cursor.fetchall()
        conn.close()
        
        similar_cases_context = []
        for result in results:
            try:
                past_modified_report = json.loads(result[1])
                
                context_item = (
                    f"- 過去の類似ケース (修正後): {past_modified_report.get('trend', '')[:100]}...\n"
                    f"  要因: {', '.join(past_modified_report.get('factors', []))}\n"
                    f"  (修正理由: {past_modified_report.get('edit_reason', '不明')[:50]}...)\n"
                )
                similar_cases_context.append(context_item)

            except json.JSONDecodeError:
                continue
        
        if similar_cases_context:
            return "\n【過去の修正済みレポート例】\n" + "\n".join(similar_cases_context)
        return ""
    
    def get_learning_stats(self):
        """学習に関する統計情報を取得します。"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            total_reports = cursor.execute("SELECT COUNT(*) FROM weekly_reports").fetchone()[0]
            corrections = cursor.execute("SELECT COUNT(*) FROM weekly_reports WHERE modified_report_json IS NOT NULL").fetchone()[0]
            
            # learning_patternsテーブルの存在確認
            try:
                total_patterns = cursor.execute("SELECT COUNT(*) FROM learning_patterns").fetchone()[0]
            except Exception as e:
                print(f"learning_patternsテーブルエラー: {e}")
                total_patterns = 0
            
            conn.close()
            
            return {
                'total_reports': total_reports,
                'corrections': corrections,
                'patterns': total_patterns
            }
        except Exception as e:
            print(f"get_learning_stats エラー: {e}")
            return {
                'total_reports': 0,
                'corrections': 0,
                'patterns': 0
            }

def save_draft_data(store_name: str, monday_date_str: str, daily_reports_data: Dict, topics: str = "", impact_day: str = "", quantitative_data: str = "", generated_report: Dict = None):
    """入力途中のデータを自動保存する"""
    try:
        store_id = db_manager.get_store_id_by_name(store_name)
        
        # 既存レポートがあるかチェック
        existing_report = db_manager.get_weekly_report(store_id, monday_date_str)
        
        # 選択された店舗のデータのみを保存（店舗キーなしの構造）
        # daily_reports_dataから該当店舗のデータを抽出
        store_daily_reports = daily_reports_data.get(store_name, {})
        
        # 週の7日分を初期化（必要に応じて）
        if not store_daily_reports:
            date_obj = datetime.strptime(monday_date_str, '%Y-%m-%d').date()
            store_daily_reports = {}
            for i in range(7):
                current_date = date_obj + timedelta(days=i)
                date_str = current_date.strftime('%Y-%m-%d')
                store_daily_reports[date_str] = {"trend": "", "factors": []}
        
        # データ構造の検証と修正（複数店舗データが混在している場合の対処）
        clean_daily_reports = {}
        for key, value in store_daily_reports.items():
            # 日付形式のキーのみを保持（YYYY-MM-DD形式）
            if isinstance(key, str) and len(key) == 10 and key.count('-') == 2:
                try:
                    datetime.strptime(key, '%Y-%m-%d')  # 日付形式を検証
                    if isinstance(value, dict):
                        clean_daily_reports[key] = value
                except ValueError:
                    pass  # 無効な日付形式は無視
        
        # 修正内容の自動保存も実行（新しい方法を使用）
        auto_save_modification()
        
        draft_data = {
            'daily_reports': clean_daily_reports,  # 清浄化されたデータのみ保存
            'topics': topics or (existing_report.get('topics', '') if existing_report else ''),
            'impact_day': impact_day or (existing_report.get('impact_day', '') if existing_report else ''),
            'quantitative_data': quantitative_data or (existing_report.get('quantitative_data', '') if existing_report else '')
        }
        
        # 既存の生成レポートと修正レポートは保持、新しいレポートがあれば更新
        original_report = generated_report if generated_report else (existing_report.get('generated_report', {}) if existing_report else {})
        modified_report = existing_report.get('modified_report') if existing_report else None
        
        # データを保存
        db_manager.save_weekly_data(
            store_id,
            monday_date_str,
            draft_data,
            original_report,
            modified_report
        )
        
        # 保存時刻を記録（日本時間）
        japan_time = get_japan_time()
        st.session_state['last_auto_save'] = japan_time.strftime('%Y年%m月%d日 %H:%M:%S')
        st.session_state['last_auto_save_timestamp'] = japan_time.timestamp()
        
        return True
    except Exception as e:
        print(f"自動保存エラー: {str(e)}")
        return False


def get_weekly_key(store_name, monday_date):
    """週次データのキーを生成"""
    return f"{store_name}_{monday_date}"

def get_weekly_additional_data(store_name, monday_date, field):
    """指定された店舗・週の追加情報を取得"""
    key = get_weekly_key(store_name, monday_date)
    return st.session_state['weekly_additional_data'].get(key, {}).get(field, "")

def set_weekly_additional_data(store_name, monday_date, field, value):
    """指定された店舗・週の追加情報を設定"""
    key = get_weekly_key(store_name, monday_date)
    if key not in st.session_state['weekly_additional_data']:
        st.session_state['weekly_additional_data'][key] = {}
    st.session_state['weekly_additional_data'][key][field] = value

def get_weekly_report_output(store_name, monday_date, field):
    """指定された店舗・週のレポート出力データを取得"""
    key = get_weekly_key(store_name, monday_date)
    return st.session_state['weekly_report_outputs'].get(key, {}).get(field, None)

def set_weekly_report_output(store_name, monday_date, field, value):
    """指定された店舗・週のレポート出力データを設定"""
    key = get_weekly_key(store_name, monday_date)
    if key not in st.session_state['weekly_report_outputs']:
        st.session_state['weekly_report_outputs'][key] = {}
    st.session_state['weekly_report_outputs'][key][field] = value


def render_weekly_additional_info(store_name: str, monday_of_week: datetime):
    """週次追加情報入力UIを描画する関数（店舗別）- マルチデバイス対応"""
    current_monday = monday_of_week.strftime('%Y-%m-%d')
    
    # マルチデバイスセッション初期化
    session_id = init_multi_device_session(store_name)
    
    # アクティブなデバイス表示
    show_active_devices(store_name)
    
    # 他のデバイスからの更新をチェック
    sync_updates = get_sync_updates(store_name, current_monday)
    
    # 現在の値を新しいデータ構造から取得（後方互換性のため旧形式も確認）
    current_topics = get_weekly_additional_data(store_name, current_monday, 'topics')
    current_impact_day = get_weekly_additional_data(store_name, current_monday, 'impact_day')
    current_quantitative_data = get_weekly_additional_data(store_name, current_monday, 'quantitative_data')
    
    # 後方互換性: 新しいデータ構造に値がない場合は旧形式から取得
    if not current_topics and store_name == st.session_state.get('selected_store_for_report'):
        current_topics = st.session_state.get('topics_input', '')
        if current_topics:
            set_weekly_additional_data(store_name, current_monday, 'topics', current_topics)
    
    if not current_impact_day and store_name == st.session_state.get('selected_store_for_report'):
        current_impact_day = st.session_state.get('impact_day_input', '')
        if current_impact_day:
            set_weekly_additional_data(store_name, current_monday, 'impact_day', current_impact_day)
    
    if not current_quantitative_data and store_name == st.session_state.get('selected_store_for_report'):
        current_quantitative_data = st.session_state.get('quantitative_data_input', '')
        if current_quantitative_data:
            set_weekly_additional_data(store_name, current_monday, 'quantitative_data', current_quantitative_data)
    
    # 同期データがある場合、ローカルデータを更新
    if 'topics' in sync_updates and 'topics' in sync_updates['topics']:
        current_topics = sync_updates['topics']['topics']['value']
        set_weekly_additional_data(store_name, current_monday, 'topics', current_topics)
    
    if 'impact_day' in sync_updates and 'impact_day' in sync_updates['impact_day']:
        current_impact_day = sync_updates['impact_day']['impact_day']['value']
        set_weekly_additional_data(store_name, current_monday, 'impact_day', current_impact_day)
    
    if 'quantitative_data' in sync_updates and 'quantitative_data' in sync_updates['quantitative_data']:
        current_quantitative_data = sync_updates['quantitative_data']['quantitative_data']['value']
        set_weekly_additional_data(store_name, current_monday, 'quantitative_data', current_quantitative_data)
    
    # 同期ボタン
    col1, col2 = st.columns([3, 1])
    with col2:
        auto_refresh_data(store_name, "weekly")
    
    # 他のデバイスからの更新通知
    if 'topics' in sync_updates:
        st.info("🔄 TOPICSが他のデバイスで更新されました")
    if 'impact_day' in sync_updates:
        st.info("🔄 インパクトデーが他のデバイスで更新されました")
    if 'quantitative_data' in sync_updates:
        st.info("🔄 定量データが他のデバイスで更新されました")
    
    # TOPICS入力
    new_topics = st.text_area(
        f"**TOPICS ({store_name}店用):** 週全体を通して特筆すべき事項や出来事を入力してください。",
        value=current_topics,
        height=100,
        key=f"topics_input_field_{store_name}"
    )
    if new_topics != current_topics:
        # 新しいデータ構造に保存
        set_weekly_additional_data(store_name, current_monday, 'topics', new_topics)
        # マルチデバイス同期
        sync_field_update(store_name, current_monday, 'topics', 'topics', new_topics)
        # 後方互換性のため、最初に選択された店舗の場合は旧形式も更新
        if store_name == st.session_state.get('selected_store_for_report'):
            st.session_state['topics_input'] = new_topics
        # 即座に自動保存（リアルタイム保存）
        save_draft_data(
            store_name,
            current_monday,
            {store_name: st.session_state['daily_reports_input'][store_name]},
            new_topics,
            get_weekly_additional_data(store_name, current_monday, 'impact_day') or st.session_state.get('impact_day_input', ''),
            get_weekly_additional_data(store_name, current_monday, 'quantitative_data') or st.session_state.get('quantitative_data_input', '')
        )
    
    # インパクト大入力
    new_impact_day = st.text_area(
        f"**インパクト大 ({store_name}店用):** 特に影響の大きかった日やイベント、その内容を記述してください。",
        value=current_impact_day,
        height=100,
        key=f"impact_day_input_field_{store_name}"
    )
    if new_impact_day != current_impact_day:
        # 新しいデータ構造に保存
        set_weekly_additional_data(store_name, current_monday, 'impact_day', new_impact_day)
        # マルチデバイス同期
        sync_field_update(store_name, current_monday, 'impact_day', 'impact_day', new_impact_day)
        # 後方互換性のため、最初に選択された店舗の場合は旧形式も更新
        if store_name == st.session_state.get('selected_store_for_report'):
            st.session_state['impact_day_input'] = new_impact_day
        # 即座に自動保存（リアルタイム保存）
        save_draft_data(
            store_name,
            current_monday,
            {store_name: st.session_state['daily_reports_input'][store_name]},
            get_weekly_additional_data(store_name, current_monday, 'topics') or st.session_state.get('topics_input', ''),
            new_impact_day,
            get_weekly_additional_data(store_name, current_monday, 'quantitative_data') or st.session_state.get('quantitative_data_input', '')
        )
    
    # 定量データ入力（事前定義項目）
    st.markdown(f"**定量データ ({store_name}店用):** 各項目に数値（％）を入力してください。")
    
    # 定量データ項目の定義
    quantitative_items = [
        "売上",
        "入店客数", 
        "買上客数",
        "買上率",
        "SET率",
        "客単価",
        "販売単価"
    ]
    
    # セッションステートで定量データを管理
    quantitative_key = f"quantitative_data_{store_name}_{current_monday}"
    if quantitative_key not in st.session_state:
        # 既存データがあれば解析して初期化
        existing_data = current_quantitative_data
        st.session_state[quantitative_key] = {}
        if existing_data:
            # 既存のテキストデータから数値を抽出（可能な場合）
            for item in quantitative_items:
                st.session_state[quantitative_key][item] = ""
        else:
            for item in quantitative_items:
                st.session_state[quantitative_key][item] = ""
    
    # 各項目の入力フィールドを作成
    quantitative_data_changed = False
    cols = st.columns(2)  # 2列レイアウト
    
    for i, item in enumerate(quantitative_items):
        with cols[i % 2]:
            old_value = st.session_state[quantitative_key].get(item, "")
            new_value = st.text_input(
                f"{item} ％",
                value=old_value,
                key=f"quant_{item}_{store_name}_{current_monday}",
                placeholder="数値のみ"
            )
            if new_value != old_value:
                st.session_state[quantitative_key][item] = new_value
                quantitative_data_changed = True
    
    # 定量データを文字列形式に変換
    quantitative_items_list = []
    for item in quantitative_items:
        value = st.session_state[quantitative_key].get(item, "")
        if value.strip():
            quantitative_items_list.append(f"{item}: {value}%")
    
    new_quantitative_data = "\n".join(quantitative_items_list)
    
    # データが変更された場合の処理
    if quantitative_data_changed or new_quantitative_data != current_quantitative_data:
        # 新しいデータ構造に保存
        set_weekly_additional_data(store_name, current_monday, 'quantitative_data', new_quantitative_data)
        # マルチデバイス同期
        sync_field_update(store_name, current_monday, 'quantitative_data', 'quantitative_data', new_quantitative_data)
        # 後方互換性のため、最初に選択された店舗の場合は旧形式も更新
        if store_name == st.session_state.get('selected_store_for_report'):
            st.session_state['quantitative_data_input'] = new_quantitative_data
        # 即座に自動保存（リアルタイム保存）
        save_draft_data(
            store_name,
            current_monday,
            {store_name: st.session_state['daily_reports_input'][store_name]},
            get_weekly_additional_data(store_name, current_monday, 'topics') or '',
            get_weekly_additional_data(store_name, current_monday, 'impact_day') or '',
            new_quantitative_data
        )


def render_daily_report_input(store_name: str, monday_of_week: datetime):
    """日次レポート入力UIを描画する関数（店舗別）- マルチデバイス対応"""
    
    # マルチデバイスセッション初期化
    session_id = init_multi_device_session(store_name)
    monday_str = monday_of_week.strftime('%Y-%m-%d')
    
    # アクティブなデバイス表示
    show_active_devices(store_name)
    
    # 他のデバイスからの更新をチェック
    sync_updates = get_sync_updates(store_name, monday_str)
    
    # 選択された店舗のdaily_reports_inputを確実に初期化
    if store_name not in st.session_state['daily_reports_input']:
        st.session_state['daily_reports_input'][store_name] = {
            (monday_of_week + timedelta(days=i)).strftime('%Y-%m-%d'): {"trend": "", "factors": []} for i in range(7)
        }

    # 同期データがある場合、ローカルデータを更新
    if 'daily_trend' in sync_updates:
        for date_key, update_data in sync_updates['daily_trend'].items():
            if date_key in st.session_state['daily_reports_input'][store_name]:
                st.session_state['daily_reports_input'][store_name][date_key]['trend'] = update_data['value']
    
    if 'daily_factors' in sync_updates:
        for date_key, update_data in sync_updates['daily_factors'].items():
            if date_key in st.session_state['daily_reports_input'][store_name]:
                factors_list = json.loads(update_data['value']) if update_data['value'] else []
                st.session_state['daily_reports_input'][store_name][date_key]['factors'] = factors_list

    # 同期ボタン
    col1, col2 = st.columns([3, 1])
    with col2:
        auto_refresh_data(store_name, "daily")
    
    # 選択された店舗の日次レポート入力欄のみを表示
    for j in range(7): # 月曜日から日曜日まで
        current_date = monday_of_week + timedelta(days=j)
        date_str = current_date.strftime('%Y-%m-%d')
        day_name = ["月", "火", "水", "木", "金", "土", "日"][j]

        st.subheader(f"🗓️ {current_date.strftime('%Y年%m月%d日')} ({day_name})")
        
        # 他のデバイスから最近更新された場合の表示
        if 'daily_trend' in sync_updates and date_str in sync_updates['daily_trend']:
            update_info = sync_updates['daily_trend'][date_str]
            st.info(f"🔄 他のデバイスで更新: {update_info['updated'][:19]}")
        
        if 'daily_factors' in sync_updates and date_str in sync_updates['daily_factors']:
            update_info = sync_updates['daily_factors'][date_str]
            st.info(f"🔄 要因が他のデバイスで更新: {update_info['updated'][:19]}")
        
        # date_str辞書の初期化を確保
        if date_str not in st.session_state['daily_reports_input'][store_name]:
            st.session_state['daily_reports_input'][store_name][date_str] = {"trend": "", "factors": []}
        
        # 日次動向（保存済みデータを確実に表示）
        current_trend_value = st.session_state['daily_reports_input'][store_name].get(date_str, {}).get('trend', '')
        trend_value = st.text_area(
            f"**{current_date.strftime('%m/%d')} 動向:**",
            value=current_trend_value,
            key=f"{store_name}_{date_str}_trend",
            height=80
        )
        
        # 値が変更された場合に自動保存とマルチデバイス同期
        if trend_value != current_trend_value:
            st.session_state['daily_reports_input'][store_name][date_str]['trend'] = trend_value
            # 他のデバイスと同期
            sync_field_update(store_name, monday_str, 'daily_trend', date_str, trend_value)
            # 即座に保存
            current_monday = monday_of_week.strftime('%Y-%m-%d')
            save_draft_data(
                store_name,
                current_monday,
                {store_name: st.session_state['daily_reports_input'][store_name]},
                get_weekly_additional_data(store_name, current_monday, 'topics') or '',
                get_weekly_additional_data(store_name, current_monday, 'impact_day') or '',
                get_weekly_additional_data(store_name, current_monday, 'quantitative_data') or ''
            )
            
        # 日次要因（保存済みデータを確実に表示）
        current_factors = st.session_state['daily_reports_input'][store_name].get(date_str, {}).get('factors', [])
        factors_str = ", ".join(current_factors)
        new_factors_str = st.text_input(
            f"**{current_date.strftime('%m/%d')} 要因 (カンマ区切り):**",
            value=factors_str,
            key=f"{store_name}_{date_str}_factors"
        )
        
        # 値が変更された場合に自動保存とマルチデバイス同期
        new_factors_list = [f.strip() for f in new_factors_str.split(',') if f.strip()]
        if new_factors_list != current_factors:
            st.session_state['daily_reports_input'][store_name][date_str]['factors'] = new_factors_list
            # 他のデバイスと同期
            sync_field_update(store_name, monday_str, 'daily_factors', date_str, json.dumps(new_factors_list))
            # 即座に保存
            current_monday = monday_of_week.strftime('%Y-%m-%d')
            save_draft_data(
                store_name,
                current_monday,
                {store_name: st.session_state['daily_reports_input'][store_name]},
                get_weekly_additional_data(store_name, current_monday, 'topics') or '',
                get_weekly_additional_data(store_name, current_monday, 'impact_day') or '',
                get_weekly_additional_data(store_name, current_monday, 'quantitative_data') or ''
            )
    
    # 日次データ入力完了後に自動保存（全ての日付の入力が完了してから実行）
    # デバウンス処理: 入力中の保存を避けるため、全日付ループ完了後に一度だけ保存
    auto_save_triggered = False
    for i in range(7):
        check_date = monday_of_week + timedelta(days=i)
        check_date_str = check_date.strftime('%Y-%m-%d')
        if (st.session_state['daily_reports_input'][store_name].get(check_date_str, {}).get('trend') or 
            st.session_state['daily_reports_input'][store_name].get(check_date_str, {}).get('factors')):
            auto_save_triggered = True
            break
    
    if auto_save_triggered:
        # 現在選択中の店舗・週の追加情報を使用
        current_monday = monday_of_week.strftime('%Y-%m-%d')
        
        save_draft_data(
            store_name,
            current_monday,
            {store_name: st.session_state['daily_reports_input'][store_name]},
            get_weekly_additional_data(store_name, current_monday, 'topics') or '',
            get_weekly_additional_data(store_name, current_monday, 'impact_day') or '',
            get_weekly_additional_data(store_name, current_monday, 'quantitative_data') or ''
        )
    
    # 日次データ入力完了後に自動保存（即座に保存）
    # 入力が変更された場合は即座に保存する
    current_monday = monday_of_week.strftime('%Y-%m-%d')
    save_draft_data(
        store_name,
        current_monday,
        {store_name: st.session_state['daily_reports_input'][store_name]},
        get_weekly_additional_data(store_name, current_monday, 'topics') or '',
        get_weekly_additional_data(store_name, current_monday, 'impact_day') or '',
        get_weekly_additional_data(store_name, current_monday, 'quantitative_data') or ''
    )


class ApparelReportGenerator:
    def __init__(self):
        self.openai_client = None
        self.training_data = None
        self.text_training_data = None 
        self.memory_db = None 
        self.learning_engine = None
        
    def set_dependencies(self, memory_db_instance, learning_engine_instance):
        """外部から依存関係を設定するためのメソッド"""
        self.memory_db = memory_db_instance
        self.learning_engine = learning_engine_instance

    def initialize_openai(self, api_key: str):
        """OpenAI APIクライアントを初期化"""
        try:
            # APIキーの基本的なフォーマットチェック
            if not api_key or len(api_key.strip()) == 0:
                st.error("❌ OpenAI APIキーが空です。")
                return False
                
            api_key = api_key.strip()  # 前後の空白を除去
            
            if not api_key.startswith('sk-'):
                st.error("❌ OpenAI APIキーが無効です。APIキーは 'sk-' で始まる必要があります。")
                return False
            
            # OpenAIクライアントを初期化（タイムアウト設定追加）
            self.openai_client = openai.OpenAI(
                api_key=api_key,
                timeout=60.0  # 60秒でタイムアウト
            )
            
            # APIキーの有効性をテスト（簡単な呼び出しで確認）
            try:
                # より軽い呼び出しに変更
                test_response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1
                )
                return True
            except openai.AuthenticationError as auth_error:
                st.error(f"❌ OpenAI APIキーが無効です: {str(auth_error)}")
                return False
            except openai.PermissionDeniedError as perm_error:
                st.error(f"❌ OpenAI APIキーの権限が不足しています: {str(perm_error)}")
                return False
            except openai.RateLimitError as rate_error:
                st.error(f"❌ OpenAI APIの利用制限に達しています: {str(rate_error)}")
                return False
            except Exception as api_error:
                st.error(f"❌ OpenAI API接続エラー: {str(api_error)} (タイプ: {type(api_error).__name__})")
                return False
                
        except Exception as e:
            st.error(f"❌ OpenAI API初期化エラー: {str(e)} (タイプ: {type(e).__name__})")
            return False
        
    def load_training_data(self, csv_file_path):
        """ファインチューニング用CSVデータを読み込み"""
        try:
            # CSVファイルを読み込み、最初の行をスキップする場合の処理
            self.training_data = pd.read_csv(csv_file_path, skiprows=1 if csv_file_path == "training_data.csv" else 0)
            # データの整合性をチェック
            if self.training_data.empty:
                try:
                    # Streamlitコンテキストがある場合のみst.warningを実行
                    st.warning(f"学習データ '{csv_file_path}' が空です。")
                except:
                    pass
                return False
            return True
        except Exception as e:
            try:
                # Streamlitコンテキストがある場合のみst.errorを実行
                st.error(f"学習データ読み込みエラー: {str(e)}")
            except:
                pass
            return False
    
    def load_text_training_data(self, csv_file_path):
        """テキスト学習データを読み込み"""
        try:
            # text_training_data.csvは特別な処理が必要
            if csv_file_path == "text_training_data.csv":
                self.text_training_data = pd.read_csv(csv_file_path, skiprows=2)  # 最初の2行をスキップ
            else:
                self.text_training_data = pd.read_csv(csv_file_path)
            
            # データの整合性をチェック
            if self.text_training_data.empty:
                try:
                    # Streamlitコンテキストがある場合のみst.warningを実行
                    st.warning(f"テキスト学習データ '{csv_file_path}' が空です。")
                except:
                    pass
                return False
            return True
        except Exception as e:
            try:
                # Streamlitコンテキストがある場合のみst.errorを実行
                st.error(f"テキスト学習データ読み込みエラー: {str(e)}")
            except:
                pass
            return False
    
    
    def validate_quantitative_data_consistency(self, daily_reports: Dict, quantitative_data: str) -> Dict:
        """定量データと日次レポートの整合性をチェック"""
        consistency_issues = []
        validation_notes = []
        
        if not quantitative_data or not daily_reports:
            return {
                'is_consistent': True,
                'issues': [],
                'notes': ['定量データまたは日次レポートが不足しているため、整合性チェックをスキップしました。']
            }
        
        # 定量データから数値を抽出し、前年比として解釈
        quantitative_items = {}
        quantitative_changes = {}  # 前年比から増減率を計算
        for line in quantitative_data.split('\n'):
            if ':' in line:
                item, value = line.split(':', 1)
                item = item.strip()
                value = value.strip().replace('%', '').replace('％', '')
                try:
                    ratio_value = float(value)  # 前年比の値（例：97% = 97）
                    change_rate = ratio_value - 100  # 増減率に変換（例：97 - 100 = -3%）
                    quantitative_items[item] = ratio_value
                    quantitative_changes[item] = change_rate
                except ValueError:
                    continue
        
        # 日次レポートから売上関連のキーワードを検索
        daily_content = ""
        for day_data in daily_reports.values():
            if isinstance(day_data, dict):
                trend = day_data.get('trend', '')
                factors = day_data.get('factors', [])
                daily_content += f"{trend} {' '.join(factors) if isinstance(factors, list) else factors} "
        
        # 整合性チェックロジック
        # 1. 売上が大幅に増減している場合の要因チェック
        if '売上' in quantitative_changes:
            sales_change = quantitative_changes['売上']
            sales_ratio = quantitative_items['売上']
            if abs(sales_change) > 10:  # 10ポイント以上の変動
                if sales_change > 10:
                    # 売上増加の場合（前年比110%以上）
                    positive_keywords = ['好調', '増加', '上昇', '伸長', '向上', '改善', 'プラス']
                    if not any(keyword in daily_content for keyword in positive_keywords):
                        consistency_issues.append(f"売上が前年比{sales_ratio}%（{sales_change:+.1f}ポイント）と増加しているが、日次レポートに売上向上の記述が見当たりません。")
                else:
                    # 売上減少の場合（前年比90%未満）
                    negative_keywords = ['不調', '減少', '下降', '低下', '悪化', 'マイナス', '苦戦']
                    if not any(keyword in daily_content for keyword in negative_keywords):
                        consistency_issues.append(f"売上が前年比{sales_ratio}%（{sales_change:+.1f}ポイント）と減少しているが、日次レポートに売上不振の記述が見当たりません。")
        
        # 2. 客数と買上客数の関係チェック
        if '入店客数' in quantitative_changes and '買上客数' in quantitative_changes:
            store_visitors_change = quantitative_changes['入店客数']
            buyers_change = quantitative_changes['買上客数']
            store_visitors_ratio = quantitative_items['入店客数']
            buyers_ratio = quantitative_items['買上客数']
            if abs(store_visitors_change - buyers_change) > 20:  # 大きな差がある場合
                validation_notes.append(f"入店客数の変動（前年比{store_visitors_ratio}%、{store_visitors_change:+.1f}ポイント）と買上客数の変動（前年比{buyers_ratio}%、{buyers_change:+.1f}ポイント）に{abs(store_visitors_change - buyers_change):.1f}ポイントの差があります。")
        
        # 3. 買上率の妥当性チェック
        if '買上率' in quantitative_changes:
            conversion_change = quantitative_changes['買上率']
            conversion_ratio = quantitative_items['買上率']
            if abs(conversion_change) > 20:  # 買上率の変動が20ポイントを超える場合
                validation_notes.append(f"買上率が前年比{conversion_ratio}%（{conversion_change:+.1f}ポイント）と大幅な変動を示しています。要因の記載を確認してください。")
        
        # 4. 客単価と販売単価の関係チェック
        if '客単価' in quantitative_changes and '販売単価' in quantitative_changes:
            avg_spend_change = quantitative_changes['客単価']
            avg_price_change = quantitative_changes['販売単価']
            avg_spend_ratio = quantitative_items['客単価']
            avg_price_ratio = quantitative_items['販売単価']
            # 客単価と販売単価が逆方向に大きく動いている場合
            if (avg_spend_change > 10 and avg_price_change < -10) or (avg_spend_change < -10 and avg_price_change > 10):
                validation_notes.append(f"客単価（前年比{avg_spend_ratio}%、{avg_spend_change:+.1f}ポイント）と販売単価（前年比{avg_price_ratio}%、{avg_price_change:+.1f}ポイント）が逆方向に変動しています。SET率や購入点数の変化を確認してください。")
        
        return {
            'is_consistent': len(consistency_issues) == 0,
            'issues': consistency_issues,
            'notes': validation_notes
        }
    
    def analyze_trend_factors(self, daily_reports: Dict, topics: str, impact_day: str, quantitative_data: str) -> Dict:
        """日次レポートを分析し、動向と要因を抽出"""
        
        # 整合性チェックを実行
        consistency_check = self.validate_quantitative_data_consistency(daily_reports, quantitative_data)
        
        current_data_for_context = {
            'daily_reports': daily_reports,
            'topics': topics,
            'impact_day': impact_day,
            'quantitative_data': quantitative_data
        }
        enhanced_context = ""
        if self.memory_db and self.learning_engine:
             enhanced_context = self.memory_db.find_similar_cases(current_data_for_context)
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(daily_reports, topics, impact_day, quantitative_data, enhanced_context, consistency_check) 
        
        if not self.openai_client:
            st.error("OpenAIクライアントが初期化されていません。APIキーを確認してください。")
            return {
                'trend': 'OpenAI APIキーが設定されていないため分析できませんでした',
                'factors': ['APIキーを設定してください'],
                'questions': ['設定ページでAPIキーを正しく入力してください'],
                'consistency_check': consistency_check
            }
            
        try:
            response = self.openai_client.chat.completions.create( 
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000,
                timeout=30
            )
            
            result = response.choices[0].message.content
            parsed_result = self._parse_analysis_result(result)
            # 整合性チェック結果を結果に追加
            parsed_result['consistency_check'] = consistency_check
            return parsed_result
            
        except Exception as e:
            st.error(f"AI分析中にエラーが発生しました: {str(e)}")
            # デフォルトの分析結果を返す（整合性チェック結果も含める）
            return {
                'trend': '分析できませんでした',
                'factors': ['エラーのため分析を実行できませんでした'],
                'questions': ['再度お試しください'],
                'impact_analysis': '分析不可',
                'next_actions': '再実行を推奨します',
                'consistency_check': consistency_check
            }
            
        except openai.APIConnectionError as e:
            st.error(f"OpenAI APIへの接続に失敗しました: {str(e)}")
            return {
                'trend': 'API接続エラーのため分析できませんでした',
                'factors': ['OpenAI APIへの接続に失敗しました'],
                'questions': ['ネットワーク接続を確認してください'],
                'consistency_check': consistency_check
            }
        except openai.APIStatusError as e: # ここはopenaiモジュールレベルのエラークラスでOK
            if e.status_code == 401: # 認証エラー (Unauthorized)
                st.error("OpenAI APIキーが無効です。設定ページでAPIキーを正しく入力してください。")
                error_msg = "APIキーが無効です"
            elif e.status_code == 429: # レート制限エラー (Too Many Requests)
                st.error("OpenAI APIのリクエストがレート制限を超えました。しばらく待ってから再試行してください。")
                error_msg = "API利用制限に達しました"
            elif e.status_code == 400: # Bad Request
                st.error("リクエストが無効です。入力データを確認してください。")
                error_msg = "リクエストが無効です"
            elif e.status_code == 500: # Server Error
                st.error("OpenAI APIサーバーエラーが発生しました。時間をおいて再試行してください。")
                error_msg = "APIサーバーエラーです"
            else:
                st.error(f"OpenAI APIエラー: {e.status_code} - {e.response}")
                error_msg = f"APIエラー ({e.status_code})"
            
            return {
                'trend': f'{error_msg}のため分析できませんでした',
                'factors': ['APIエラーが発生しました'],
                'questions': ['設定を確認して再試行してください'],
                'consistency_check': consistency_check
            }
        except openai.APITimeoutError: # タイムアウトエラー
            st.error("OpenAI APIへのリクエストがタイムアウトしました。ネットワーク接続を確認し、再試行してください。")
            return {
                'trend': 'APIタイムアウトのため分析できませんでした',
                'factors': ['APIリクエストがタイムアウトしました'],
                'questions': ['ネットワーク接続を確認して再試行してください'],
                'consistency_check': consistency_check
            }
        except Exception as e:
            st.error(f"AI分析エラー: {str(e)}")
            return {
                'trend': f'予期しないエラーのため分析できませんでした: {str(e)}',
                'factors': ['システムエラーが発生しました'],
                'questions': ['管理者に連絡してください'],
                'consistency_check': consistency_check
            }
        
    
    def _build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        base_prompt = """
        あなたはアパレル小売業界の専門アナリストです。
        与えられた日次レポートデータ、TOPICS、インパクト大、定量データを基に、週次レポートを作成してください。

        【分析要件】
        1.  動向と要因の因果関係を明確に記述する。
        2.  「目論見以下」などの結果表現は、具体的な要因まで深掘りして説明する。
        3.  提供された定量データ（売上、入店客数、買上客数、買上率、SET率、客単価、販売単価の各％）との整合性を確認し、レポートに反映させる。
        4.  定量データ整合性チェック結果が提供された場合は、その指摘事項を考慮してレポートを作成する。
        5.  TOPICSやインパクト大の事象が週全体に与えた影響度を評価し、レポートに含める。
        6.  敬語・丁寧語は使用せず、体言止めや簡潔な表現で記述する。アパレル店舗の上位部署が理解しやすい簡潔な文体とする。
        7.  週全体の動向として、**指定された店舗の情報を中心に**分析する。（他の店舗の情報は参考程度にとどめる）

        【出力形式】
        必ず以下のJSON形式で出力する。
        ```json
        {
            "trend": "週全体の動向を400字程度で記述。各店舗の動向と要因、定量データ、TOPICS、インパクト大を統合し、因果関係を重視して説明。敬語・丁寧語は使用せず、体言止めや簡潔な表現で記述。",
            "factors": [
                "最も影響の大きかった要因1 (30字以内)",
                "次に影響の大きかった要因2 (30字以内)",
                "3番目に影響の大きかった要因3 (30字以内)"
            ],
            "questions": [
                "不明点や追加確認が必要な項目があれば、簡潔な質問形式で記述。なければ空の配列。"
            ]
        }
        ```
        - 「trend」は400字程度を厳守し、敬語・丁寧語（です・ます調）は使用しない。
        - 「factors」は最大3つまでとし、それぞれ30字以内とする。
        - JSON形式以外での出力は厳禁。
        """
        
        if self.training_data is not None and not self.training_data.empty:
            training_context = self._extract_training_context()
            if training_context:
                base_prompt += f"\n\n【社内用語・文体・過去の類似例の参考情報】\n{training_context}"
        
        return base_prompt
    
    def _build_user_prompt(self, daily_reports: Dict, topics: str, impact_day: str, quantitative_data: str, enhanced_context: str, consistency_check: Dict = None) -> str:
        """ユーザープロンプトを構築"""
        prompt = "以下の情報から週次レポートをJSON形式で作成する。文体は敬語・丁寧語を使用せず、体言止めや簡潔な表現で記述する。\n\n"
        
        # 修正: daily_reports は既に単一店舗のデータになっていることを想定
        prompt += "【日次レポートデータ】\n"
        # daily_reports は { '店舗名': { '日付': { 'trend': '', 'factors': [] } } の形式で来ると想定
        for store, data in daily_reports.items(): # このループは一度しか回らないはず
            prompt += f"- **{store}店**:\n"
            for date, report in data.items():
                # 安全なアクセスに修正
                if isinstance(report, dict):
                    trend_text = report.get('trend', '') if report.get('trend', '') else "未入力"
                    factors_text = ", ".join(report.get('factors', [])) if report.get('factors', []) else "なし"
                else:
                    trend_text = "データ形式エラー"
                    factors_text = "データ形式エラー"
                prompt += f"  - {date}: 動向={trend_text}, 要因={factors_text}\n"
        
        if topics:
            prompt += f"\n【TOPICS】\n{topics}\n"
        
        if impact_day:
            prompt += f"\n【インパクト大】\n{impact_day}\n"
        
        if quantitative_data:
            prompt += f"\n【定量データ】\n{quantitative_data}\n"
        
        # 整合性チェック結果を追加
        if consistency_check:
            if not consistency_check['is_consistent'] or consistency_check['notes']:
                prompt += f"\n【定量データ整合性チェック結果】\n"
                if not consistency_check['is_consistent']:
                    prompt += "⚠️ 整合性の問題が検出されました:\n"
                    for issue in consistency_check['issues']:
                        prompt += f"- {issue}\n"
                if consistency_check['notes']:
                    prompt += "📊 注意事項:\n"
                    for note in consistency_check['notes']:
                        prompt += f"- {note}\n"
                prompt += "上記の整合性チェック結果を考慮してレポートを作成する。\n"
        
        if enhanced_context:
            prompt += f"\n{enhanced_context}\n" 
        
        return prompt
    
    def _extract_training_context(self) -> str:
        """学習データから社内用語・文体を抽出 (簡略化された例)"""
        if self.training_data is None or self.training_data.empty:
            if self.text_training_data is None or self.text_training_data.empty:
                return ""
        
        context = []
        
        # 既存のtraining_data.csvからの文脈作成
        if self.training_data is not None and not self.training_data.empty:
            # カラム名を確認して適切に処理
            training_columns = self.training_data.columns.tolist()
            
            # example_trend または trend_patterns カラムがある場合
            trend_col = None
            if 'example_trend' in training_columns:
                trend_col = 'example_trend'
            elif 'trend_patterns' in training_columns:
                trend_col = 'trend_patterns'
            
            if trend_col and not self.training_data[trend_col].empty:
                context.append("過去のレポート記述例 (動向):")
                for ex in self.training_data[trend_col].dropna().head(3):
                    if ex and str(ex).strip():
                        context.append(f"- {str(ex)[:50]}...")
            
            # example_factors または factor_patterns カラムがある場合
            factor_col = None
            if 'example_factors' in training_columns:
                factor_col = 'example_factors'
            elif 'factor_patterns' in training_columns:
                factor_col = 'factor_patterns'
                
            if factor_col and not self.training_data[factor_col].empty:
                context.append("過去のレポート記述例 (要因):")
                for ex in self.training_data[factor_col].dropna().head(3):
                    if ex and str(ex).strip():
                        context.append(f"- {str(ex)[:30]}...")
            
            # expected_output カラムがある場合
            if 'expected_output' in training_columns and not self.training_data['expected_output'].empty:
                context.append("過去のレポート記述例 (期待出力):")
                for ex in self.training_data['expected_output'].dropna().head(3):
                    if ex and str(ex).strip():
                        context.append(f"- {str(ex)[:60]}...")
        
        # text_training_data.csvからの文脈作成
        if self.text_training_data is not None and not self.text_training_data.empty:
            text_columns = self.text_training_data.columns.tolist()
            
            if 'output' in text_columns and not self.text_training_data['output'].empty:
                context.append("過去のレポート記述例 (テキスト学習データ):")
                for ex in self.text_training_data['output'].dropna().head(3):
                    if ex and str(ex).strip():
                        context.append(f"- {str(ex)[:60]}...")
        
        return "\n".join(context)
    
    def _parse_analysis_result(self, result: str) -> Dict:
        """分析結果（JSON文字列）をパース"""
        parsed = {
            'trend': '',
            'factors': [],
            'questions': [],
            'original_result_raw': result # LLMの生の出力を保持
        }
        
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
        if not json_match:
            try:
                json_data = json.loads(result)
            except json.JSONDecodeError as e:
                # JSONパースエラーの場合、エラーメッセージをtrendフィールドに設定
                error_msg = f"エラー: AIからの出力が有効なJSON形式ではありませんでした。生の出力: {result[:200]}..."
                parsed['trend'] = error_msg
                try:
                    # Streamlitコンテキストがある場合のみst.errorを実行
                    st.error("AIからの出力が有効なJSON形式ではありませんでした。開発者向け情報: \n" + result)
                except:
                    # Streamlitコンテキスト外では無視
                    pass
                return parsed
        else:
            try:
                json_string = json_match.group(1)
                json_data = json.loads(json_string)
            except json.JSONDecodeError as e:
                # JSONパースエラーの場合、エラーメッセージをtrendフィールドに設定
                error_msg = f"エラー: AIからのJSON出力のパースに失敗しました。生の出力: {json_string[:200]}..."
                parsed['trend'] = error_msg
                try:
                    # Streamlitコンテキストがある場合のみst.errorを実行
                    st.error("AIからのJSON出力のパースに失敗しました。開発者向け情報: \n" + json_string)
                except:
                    # Streamlitコンテキスト外では無視
                    pass
                return parsed

        parsed['trend'] = json_data.get('trend', '').strip()
        parsed['factors'] = [f.strip() for f in json_data.get('factors', []) if f.strip()][:3]
        parsed['questions'] = [q.strip() for q in json_data.get('questions', []) if q.strip()]
        
        return parsed

    def generate_weekly_report(self, data_for_ai: Dict) -> Dict:
        """週次レポートを生成するメインメソッド"""
        try:
            # analyze_trend_factorsメソッドを使用してレポートを生成
            return self.analyze_trend_factors(
                daily_reports=data_for_ai.get('daily_reports', {}),
                topics=data_for_ai.get('topics', ''),
                impact_day=data_for_ai.get('impact_day', ''),
                quantitative_data=data_for_ai.get('quantitative_data', '')
            )
        except Exception as e:
            st.error(f"週次レポート生成中にエラーが発生しました: {str(e)}")
            return {
                'trend': f'レポート生成エラー: {str(e)}',
                'factors': ['システムエラーが発生しました'],
                'questions': ['管理者に連絡してください'],
                'consistency_check': {
                    'is_consistent': True,
                    'issues': [],
                    'notes': ['エラーのため整合性チェックをスキップしました']
                }
            }
        
        return parsed

class LearningEngine:
    """学習エンジンクラス。ユーザーの修正から学習パターンを生成・管理します。"""
    
    def __init__(self, db_manager: DBManager):
        self.db_manager = db_manager
    
    def learn_from_correction(self, input_data: Dict, original_output: Dict, modified_output: Dict):
        """ユーザーの修正から学習パターンを生成し、DBに保存します。"""
        # 入力コンテキストのハッシュを生成（簡易的な方法）
        input_context_str = json.dumps(input_data, ensure_ascii=False, sort_keys=True)
        input_context_hash = hashlib.sha256(input_context_str.encode('utf-8')).hexdigest()
        
        conn = self.db_manager._get_connection() # DBManagerから接続を取得
        cursor = conn.cursor()

        original_output_json = json.dumps(original_output, ensure_ascii=False)
        modified_output_json = json.dumps(modified_output, ensure_ascii=False)
        edit_reason = modified_output.get('edit_reason', '')

        cursor.execute('''
            SELECT id, usage_count FROM learning_patterns 
            WHERE input_context_hash = ? AND modified_output_json = ?
        ''', (input_context_hash, modified_output_json))
        
        existing_pattern = cursor.fetchone()

        if existing_pattern:
            pattern_id, usage_count = existing_pattern
            cursor.execute('''
                UPDATE learning_patterns 
                SET usage_count = ?, last_used = ?
                WHERE id = ?
            ''', (usage_count + 1, datetime.now().isoformat(), pattern_id))
            st.info("既存の学習パターンを更新しました。")
        else:
            cursor.execute('''
                INSERT INTO learning_patterns 
                (input_context_hash, original_output_json, modified_output_json, edit_reason, usage_count, last_used)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                input_context_hash,
                original_output_json,
                modified_output_json,
                edit_reason,
                1,
                datetime.now().isoformat()
            ))
            st.success("新しい学習パターンを保存しました！AIの精度向上に役立ちます。")
        
        conn.commit()
        conn.close()


# --- Streamlit UI Components ---

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def get_file_download_link(df, filename, text):
    """Generates a link for downloading a pandas DataFrame as CSV."""
    csv = df.to_csv(index=False, encoding='utf-8-sig') # UTF-8 BOM付きでExcel対応
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'
    return href

def get_excel_download_link(df, filename, text):
    """Generates a link for downloading a pandas DataFrame as Excel."""
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='レポート')
        b64 = base64.b64encode(output.getvalue()).decode()
        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">{text}</a>'
        return href
    except ImportError:
        # xlsxwriterが利用できない場合はCSVにフォールバック
        st.warning("Excel形式でのダウンロードができません。CSV形式でダウンロードします。")
        csv = df.to_csv(index=False, encoding='utf-8-sig')
        b64 = base64.b64encode(csv.encode()).decode()
        csv_filename = filename.replace('.xlsx', '.csv')
        href = f'<a href="data:file/csv;base64,{b64}" download="{csv_filename}">{text}</a>'
        return href

# グローバルインスタンスの初期化
db_manager = DBManager()
report_generator = ApparelReportGenerator()
learning_engine = LearningEngine(db_manager)

# 依存関係を設定
report_generator.set_dependencies(db_manager, learning_engine)

# ★ここから追加するコード★
TRAINING_CSV_FILE = "training_data.csv" # ここを実際のファイル名に置き換えてください！
TEXT_TRAINING_CSV_FILE = "text_training_data.csv" # テキスト学習データファイル

# training_data.csvの読み込み（表示なし）
if Path(TRAINING_CSV_FILE).exists():
    report_generator.load_training_data(TRAINING_CSV_FILE)
    # st.sidebar.success(f"学習データ '{TRAINING_CSV_FILE}' を読み込みました。")  # 表示削除
    # 読み込み失敗時のみエラー表示（デバッグ用）
    # else:
    #     st.sidebar.warning(f"学習データ '{TRAINING_CSV_FILE}' の読み込みに失敗しました。ファイルの内容を確認してください。")
# else:
    # st.sidebar.info(f"学習データ '{TRAINING_CSV_FILE}' が見つかりませんでした。")  # 表示削除

# text_training_data.csvの読み込み（表示なし）
if Path(TEXT_TRAINING_CSV_FILE).exists():
    report_generator.load_text_training_data(TEXT_TRAINING_CSV_FILE)
    # st.sidebar.success(f"テキスト学習データ '{TEXT_TRAINING_CSV_FILE}' を読み込みました。")  # 表示削除
    # 読み込み失敗時のみエラー表示（デバッグ用）
    # else:
    #     st.sidebar.warning(f"テキスト学習データ '{TEXT_TRAINING_CSV_FILE}' の読み込みに失敗しました。ファイルの内容を確認してください。")
# else:
    # st.sidebar.info(f"テキスト学習データ '{TEXT_TRAINING_CSV_FILE}' が見つかりませんでした。")  # 表示削除

# 学習データの有無を確認（機能は維持）
has_training_data = (report_generator.training_data is not None and not report_generator.training_data.empty)
has_text_training_data = (report_generator.text_training_data is not None and not report_generator.text_training_data.empty)

# 学習データが全くない場合のみ警告表示（重要なエラー情報として残す）
if not has_training_data and not has_text_training_data:
    st.sidebar.warning("学習データが見つかりませんでした。学習機能は無効になります。")
# ★ここまで追加するコード★

def get_monday_of_week(selected_date: date) -> date:
    """与えられた日付が属する週の月曜日を計算します。"""
    # 選択された日付の曜日を取得 (月曜日=0, 日曜日=6)
    weekday = selected_date.weekday()
    # 月曜日に戻るための日数を計算
    days_since_monday = weekday
    monday = selected_date - timedelta(days=days_since_monday)
    return monday

def get_current_week_monday() -> date:
    """現在の週の月曜日を取得します。"""
    today = date.today()
    return get_monday_of_week(today)

# --- Streamlit UI Components ---

def auto_save_modification():
    """修正内容の自動保存"""
    try:
        # 現在選択中の店舗と週の情報を取得
        store_key = st.session_state.get('selected_store_for_report', 'default')
        week_key = st.session_state.get('selected_monday', 'default')
        session_key = f"{store_key}_{week_key}"
        
        # 修正内容用のセッションキーを作成
        saved_modifications = st.session_state.get('saved_modifications', {})
        if session_key not in saved_modifications:
            saved_modifications[session_key] = {}
        
        # 修正入力フィールドの値をセッション状態に保存
        if 'modified_trend_input' in st.session_state:
            saved_modifications[session_key]['trend'] = st.session_state['modified_trend_input']
        if 'modified_factors_input' in st.session_state:
            saved_modifications[session_key]['factors'] = st.session_state['modified_factors_input']
        if 'modified_questions_input' in st.session_state:
            saved_modifications[session_key]['questions'] = st.session_state['modified_questions_input']
        if 'edit_reason_input' in st.session_state:
            saved_modifications[session_key]['edit_reason'] = st.session_state['edit_reason_input']
        
        st.session_state['saved_modifications'] = saved_modifications
        
    except Exception as e:
        pass  # エラーが発生しても処理を続行

def get_saved_modification(field: str) -> str:
    """保存された修正内容を取得"""
    try:
        store_key = st.session_state.get('selected_store_for_report', 'default')
        week_key = st.session_state.get('selected_monday', 'default')
        session_key = f"{store_key}_{week_key}"
        
        saved_modifications = st.session_state.get('saved_modifications', {})
        return saved_modifications.get(session_key, {}).get(field, '')
    except Exception:
        return ''

def clear_saved_modifications():
    """保存された修正内容をクリア"""
    try:
        store_key = st.session_state.get('selected_store_for_report', 'default')
        week_key = st.session_state.get('selected_monday', 'default')
        session_key = f"{store_key}_{week_key}"
        
        saved_modifications = st.session_state.get('saved_modifications', {})
        if session_key in saved_modifications:
            del saved_modifications[session_key]
        st.session_state['saved_modifications'] = saved_modifications
    except Exception:
        pass

def show_report_creation_page():
    st.title("📈 週次レポート作成")
    st.markdown("---")

    st.info("このページでは、店舗ごとの日次データを入力し、AIが週次レポートを生成します。AIレポートは後で修正し、システムに学習させることができます。")

    # 週の選択
    st.header("1. レポート対象週の選択")
    # 今週の月曜日をデフォルト値にする
    default_monday = get_current_week_monday()
    selected_date = st.date_input(
        "レポートを作成する週の**月曜日**を選択してください。",
        value=default_monday,
        min_value=date(2023, 1, 1),
        max_value=date.today() + timedelta(days=30), # 未来の日付も少し許容
        format="YYYY/MM/DD"
    )
    
    # 選択された日付が月曜日であることを確認し、そうでない場合は月曜日に補正
    if selected_date.weekday() != 0:
        st.warning(f"選択された日付は月曜日ではありません。自動的に**{get_monday_of_week(selected_date).strftime('%Y年%m月%d日')}**の週として処理します。")
        monday_of_week = get_monday_of_week(selected_date)
    else:
        monday_of_week = selected_date
    
    st.session_state['selected_monday'] = monday_of_week.strftime('%Y-%m-%d')
    
    # 日付が変更された場合の処理
    if 'last_selected_monday' not in st.session_state or st.session_state['last_selected_monday'] != st.session_state['selected_monday']:
        # 日付変更時は既存データ読み込みフラグをリセット
        st.session_state['topics_loaded_for_week'] = False
        # 自動保存時刻もリセット
        st.session_state['last_auto_save'] = None
    
    st.subheader(f"選択週: {monday_of_week.strftime('%Y年%m月%d日')} 〜 {(monday_of_week + timedelta(days=6)).strftime('%Y年%m月%d日')}")
    st.markdown("---")

    # 既存レポートのロード
    store_names = [s[1] for s in db_manager.get_all_stores()]
    if 'selected_store_for_report' not in st.session_state:
        st.session_state['selected_store_for_report'] = store_names[0] # デフォルトで最初の店舗

    # 複数店舗編集モードの初期化
    if 'multi_store_mode' not in st.session_state:
        st.session_state['multi_store_mode'] = False
    if 'selected_stores_for_editing' not in st.session_state:
        st.session_state['selected_stores_for_editing'] = store_names[:2]  # デフォルトで最初の2店舗

    # レポートデータ構造の初期化
    if 'daily_reports_input' not in st.session_state:
        st.session_state['daily_reports_input'] = {store_name: {} for store_name in store_names}
    
    # 週全体の追加情報を店舗ごと・週ごとに管理
    if 'weekly_additional_data' not in st.session_state:
        st.session_state['weekly_additional_data'] = {}
    
    # レポート出力データを店舗・週ごとに管理
    if 'weekly_report_outputs' not in st.session_state:
        st.session_state['weekly_report_outputs'] = {}
    
    # 複数店舗用の自動保存タイムスタンプ管理
    if 'multi_store_auto_save' not in st.session_state:
        st.session_state['multi_store_auto_save'] = {}
    
    # 後方互換性のため、旧形式のデータがあれば移行
    if 'topics_input' not in st.session_state:
        st.session_state['topics_input'] = ""
    if 'impact_day_input' not in st.session_state:
        st.session_state['impact_day_input'] = ""
    if 'quantitative_data_input' not in st.session_state:
        st.session_state['quantitative_data_input'] = ""
    
    if 'generated_report_output' not in st.session_state:
        st.session_state['generated_report_output'] = None
    if 'modified_report_output' not in st.session_state:
        st.session_state['modified_report_output'] = None
    if 'report_id_to_edit' not in st.session_state:
        st.session_state['report_id_to_edit'] = None

    # 週全体の追加情報を管理するヘルパー関数
    def get_weekly_key(store_name, monday_date):
        """店舗と週の組み合わせでキーを生成"""
        return f"{store_name}_{monday_date}"
    
    def get_weekly_additional_data(store_name, monday_date, field):
        """指定された店舗・週の追加情報を取得"""
        key = get_weekly_key(store_name, monday_date)
        return st.session_state['weekly_additional_data'].get(key, {}).get(field, "")
    
    def set_weekly_additional_data(store_name, monday_date, field, value):
        """指定された店舗・週の追加情報を設定"""
        key = get_weekly_key(store_name, monday_date)
        if key not in st.session_state['weekly_additional_data']:
            st.session_state['weekly_additional_data'][key] = {}
        st.session_state['weekly_additional_data'][key][field] = value
    
    def get_weekly_report_output(store_name, monday_date, field):
        """指定された店舗・週のレポート出力データを取得"""
        key = get_weekly_key(store_name, monday_date)
        return st.session_state['weekly_report_outputs'].get(key, {}).get(field, None)
    
    def set_weekly_report_output(store_name, monday_date, field, value):
        """指定された店舗・週のレポート出力データを設定"""
        key = get_weekly_key(store_name, monday_date)
        if key not in st.session_state['weekly_report_outputs']:
            st.session_state['weekly_report_outputs'][key] = {}
        st.session_state['weekly_report_outputs'][key][field] = value

    # 選択された週の既存レポートをロード
    # まず、ストア選択タブの現在のインデックスをセッションステートに保持
    if 'active_tab_index' not in st.session_state:
        st.session_state['active_tab_index'] = 0 # デフォルトは最初のタブ (RAY)

    # 既存レポートをロードする前に、現在選択されている店舗名を取得
    # 初期表示時や日付変更時に、選択店舗のレポートが読み込まれるように調整
    # ただし、タブのインデックスが変更された場合は、そのタブの店舗名に追従
    # ここでは、`selected_store_for_report` と `active_tab_index` の同期を強化
    
    # 各店舗の既存レポートを個別に読み込み（統一された方法）
    for store_name in store_names:
        store_id = db_manager.get_store_id_by_name(store_name)
        existing_report = db_manager.get_weekly_report(store_id, st.session_state['selected_monday'])
        
        if existing_report:
            # 新しいデータ構造（店舗キーなし）で直接日付データを設定
            if existing_report.get('daily_reports'):
                # 既存のセッションデータがない場合、または空の場合のみ上書き
                if (store_name not in st.session_state['daily_reports_input'] or 
                    not any(data.get('trend') or data.get('factors') 
                           for data in st.session_state['daily_reports_input'][store_name].values() 
                           if isinstance(data, dict))):
                    st.session_state['daily_reports_input'][store_name] = existing_report['daily_reports']
            
            # 週全体の追加情報を店舗ごと・週ごとに保存
            set_weekly_additional_data(store_name, st.session_state['selected_monday'], 'topics', existing_report.get('topics', ''))
            set_weekly_additional_data(store_name, st.session_state['selected_monday'], 'impact_day', existing_report.get('impact_day', ''))
            set_weekly_additional_data(store_name, st.session_state['selected_monday'], 'quantitative_data', existing_report.get('quantitative_data', ''))
            
            # レポート出力データも店舗・週ごとに保存
            set_weekly_report_output(store_name, st.session_state['selected_monday'], 'generated_report', existing_report.get('generated_report', {}))
            set_weekly_report_output(store_name, st.session_state['selected_monday'], 'modified_report', existing_report.get('modified_report'))
            set_weekly_report_output(store_name, st.session_state['selected_monday'], 'report_id', existing_report.get('id'))
            
            # 最初に見つかった店舗のその他データも読み込み（レポート出力データは共通→個別管理に変更）
            if not st.session_state.get('topics_loaded_for_week'):
                # 後方互換性のため旧形式も更新（現在選択中の店舗のデータで更新）
                if store_name == st.session_state.get('selected_store_for_report', store_names[0]):
                    st.session_state['topics_input'] = existing_report.get('topics', '')
                    st.session_state['impact_day_input'] = existing_report.get('impact_day', '')
                    st.session_state['quantitative_data_input'] = existing_report.get('quantitative_data', '')
                    st.session_state['generated_report_output'] = existing_report.get('generated_report', {})
                    st.session_state['modified_report_output'] = existing_report.get('modified_report')
                    st.session_state['report_id_to_edit'] = existing_report.get('id')
                st.session_state['topics_loaded_for_week'] = True
        else:
            # データがない場合は空の構造で初期化
            if store_name not in st.session_state['daily_reports_input']:
                st.session_state['daily_reports_input'][store_name] = {
                    (monday_of_week + timedelta(days=i)).strftime('%Y-%m-%d'): {"trend": "", "factors": []} for i in range(7)
                }
            
    # 既存レポートがロードされたかチェックして表示
    loaded_stores = []
    for store_name in store_names:
        if st.session_state['daily_reports_input'][store_name]:
            # 空でないデータがあるかチェック
            has_data = any(
                data.get('trend') or data.get('factors') 
                for data in st.session_state['daily_reports_input'][store_name].values()
                if isinstance(data, dict)
            )
            if has_data:
                loaded_stores.append(store_name)
    
    if loaded_stores:
        st.info(f"📁 保存済みデータを読み込みました: {', '.join(loaded_stores)}店")
    
    # 日付が変更された場合の処理（修正版）
    if 'last_selected_monday' not in st.session_state or st.session_state['last_selected_monday'] != st.session_state['selected_monday']:
        # 日付変更時は、現在の入力内容を自動保存してから新しい週のデータを読み込む
        if 'last_selected_monday' in st.session_state and st.session_state['last_selected_monday']:
            # 前の週のデータを保存
            old_monday = st.session_state['last_selected_monday']
            for store_name in store_names:
                if st.session_state['daily_reports_input'].get(store_name):
                    # 空でないデータがあるかチェック
                    has_data = any(
                        data.get('trend', '').strip() or data.get('factors') 
                        for data in st.session_state['daily_reports_input'][store_name].values()
                        if isinstance(data, dict)
                    )
                    if has_data:
                        # 前の週のデータを保存
                        topics = get_weekly_additional_data(store_name, old_monday, 'topics')
                        impact_day = get_weekly_additional_data(store_name, old_monday, 'impact_day')
                        quantitative_data = get_weekly_additional_data(store_name, old_monday, 'quantitative_data')
                        save_draft_data(store_name, old_monday, st.session_state['daily_reports_input'], topics, impact_day, quantitative_data)
        
        # 新しい週のデータを読み込み
        for store_name in store_names:
            # 既存データの読み込み（データベースから）
            store_id = db_manager.get_store_id_by_name(store_name)
            existing_report = db_manager.get_weekly_report(store_id, st.session_state['selected_monday'])
            
            # データベースに既存データがある場合はそれを使用、ない場合のみ空構造で初期化
            if existing_report and existing_report.get('daily_reports'):
                # 既存データをそのまま使用
                st.session_state['daily_reports_input'][store_name] = existing_report['daily_reports']
            else:
                # データがない場合のみ空の構造で初期化
                st.session_state['daily_reports_input'][store_name] = {
                    (monday_of_week + timedelta(days=i)).strftime('%Y-%m-%d'): {"trend": "", "factors": []} for i in range(7)
                }
            
            # 週全体の追加情報を店舗ごと・週ごとに保存
            if existing_report:
                set_weekly_additional_data(store_name, st.session_state['selected_monday'], 'topics', existing_report.get('topics', ''))
                set_weekly_additional_data(store_name, st.session_state['selected_monday'], 'impact_day', existing_report.get('impact_day', ''))
                set_weekly_additional_data(store_name, st.session_state['selected_monday'], 'quantitative_data', existing_report.get('quantitative_data', ''))
                
                # レポート出力データも店舗・週ごとに保存
                set_weekly_report_output(store_name, st.session_state['selected_monday'], 'generated_report', existing_report.get('generated_report', {}))
                set_weekly_report_output(store_name, st.session_state['selected_monday'], 'modified_report', existing_report.get('modified_report'))
                set_weekly_report_output(store_name, st.session_state['selected_monday'], 'report_id', existing_report.get('id'))
        
        # 後方互換性のため旧形式も初期化・更新（強制的に最新データに更新）
        current_store = st.session_state.get('selected_store_for_report', store_names[0])
        st.session_state['topics_input'] = get_weekly_additional_data(current_store, st.session_state['selected_monday'], 'topics')
        st.session_state['impact_day_input'] = get_weekly_additional_data(current_store, st.session_state['selected_monday'], 'impact_day')
        st.session_state['quantitative_data_input'] = get_weekly_additional_data(current_store, st.session_state['selected_monday'], 'quantitative_data')
        st.session_state['generated_report_output'] = get_weekly_report_output(current_store, st.session_state['selected_monday'], 'generated_report')
        st.session_state['modified_report_output'] = get_weekly_report_output(current_store, st.session_state['selected_monday'], 'modified_report')
        st.session_state['report_id_to_edit'] = get_weekly_report_output(current_store, st.session_state['selected_monday'], 'report_id')
        
        # データ読み込み完了フラグを設定
        st.session_state['topics_loaded_for_week'] = True
        st.session_state['last_selected_monday'] = st.session_state['selected_monday']
        
        # 週次レポートのキャッシュクリア（新しい週では新しいレポートを生成するため）
        for store_name in store_names:
            ai_report_key = f"ai_generated_report_{store_name}_{st.session_state['selected_monday']}"
            if ai_report_key in st.session_state:
                del st.session_state[ai_report_key]

    st.header("2. 日次レポートデータの入力")
    st.markdown("各店舗の**日ごとの動向と要因**を入力してください。要因は複数入力可能です（カンマ区切り）。")
    
    # 単一店舗編集モード（マルチデバイス対応）
    st.markdown("### 🏪 **店舗編集モード（マルチデバイス対応）**")
    st.markdown("選択した店舗を複数のデバイス（PC、iPhone、iPad等）から同時に編集できます。")
    
    # 編集対象店舗の選択（単一店舗）
    selected_store_for_editing = st.selectbox(
        "**編集する店舗を選択してください:**",
        store_names,
        index=store_names.index(st.session_state.get('selected_stores_for_editing', [store_names[0]])[0]) 
              if st.session_state.get('selected_stores_for_editing') else 0
    )
    
    # 単一店舗をリスト形式で格納（既存コードとの互換性）
    selected_stores_for_editing = [selected_store_for_editing]
    
    st.session_state['selected_stores_for_editing'] = selected_stores_for_editing
    st.session_state['selected_store_for_report'] = selected_store_for_editing
    
    # 店舗選択が変更された場合、その店舗のレポートデータを即座に読み込み
    if st.session_state.get('last_selected_store') != selected_store_for_editing:
        current_monday = st.session_state.get('selected_monday')
        if current_monday:
            # 選択された店舗のレポートデータを読み込み
            st.session_state['generated_report_output'] = get_weekly_report_output(selected_store_for_editing, current_monday, 'generated_report')
            st.session_state['modified_report_output'] = get_weekly_report_output(selected_store_for_editing, current_monday, 'modified_report')
            st.session_state['report_id_to_edit'] = get_weekly_report_output(selected_store_for_editing, current_monday, 'report_id')
        st.session_state['last_selected_store'] = selected_store_for_editing
    
    # 選択された店舗の表示
    st.info(f"📊 **編集中の店舗:** {selected_store_for_editing}店 - マルチデバイス同時編集対応")
    
    # 選択された店舗のデータ入力エリア
    st.markdown(f"### 📝 **{selected_store_for_editing}店のデータ入力**")
    current_store = selected_store_for_editing
    
    # 自動保存状況を表示
    if 'last_auto_save' not in st.session_state:
        st.session_state['last_auto_save'] = None
    if 'last_auto_save_timestamp' not in st.session_state:
        st.session_state['last_auto_save_timestamp'] = None
    
    if st.session_state['last_auto_save']:
        # 保存からの経過時間を計算
        if st.session_state['last_auto_save_timestamp']:
            current_time = get_japan_time().timestamp()
            elapsed_seconds = int(current_time - st.session_state['last_auto_save_timestamp'])
            
            if elapsed_seconds < 60:
                elapsed_text = f"（{elapsed_seconds}秒前）"
            elif elapsed_seconds < 3600:
                elapsed_minutes = elapsed_seconds // 60
                elapsed_text = f"（{elapsed_minutes}分前）"
            else:
                elapsed_hours = elapsed_seconds // 3600
                elapsed_text = f"（{elapsed_hours}時間前）"
        else:
            elapsed_text = ""
        
        st.success(f"✅ 自動保存済み: {st.session_state['last_auto_save']} {elapsed_text}")
    else:
        st.info("💾 入力内容は自動的に保存されます")
    
    st.markdown("---")

    # 日次レポート入力 - 単一店舗モード
    if selected_store_for_editing:
        render_daily_report_input(selected_store_for_editing, monday_of_week)
    else:
        st.warning("⚠️ 編集する店舗を選択してください。")
    
    st.markdown("---")

    st.header("3. 週全体の追加情報 (任意)")
    
    # 週次追加情報入力 - 単一店舗モード
    if selected_store_for_editing:
        render_weekly_additional_info(selected_store_for_editing, monday_of_week)
    else:
        st.warning("⚠️ 編集する店舗を選択してください。")
    
    st.markdown("---")

    # レポート出力ボタン
    st.header("4. レポート出力")
    
    # 選択された店舗のレポート出力
    if selected_store_for_editing:
        output_stores = [selected_store_for_editing]
        st.info(f"📋 出力対象店舗: {selected_store_for_editing}")
    else:
        # 店舗が選択されていない場合のフォールバック
        st.warning("⚠️ まず編集する店舗を選択してください。")
        return
    
    if st.button("📄 レポート出力", type="primary"):
        try:
            # APIキーの確認（絶対パス使用で確実に読み込み）
            script_dir = pathlib.Path(__file__).parent.absolute()
            env_path = script_dir / '.env'
            load_dotenv(dotenv_path=env_path, override=True)
            openai_api_key = os.getenv("OPENAI_API_KEY")
            
            if not openai_api_key:
                st.error("❌ OpenAI APIキーが設定されていません。システム管理者にAPIキーの設定を依頼してください。")
                st.info("管理者の方は、`.env`ファイルに`OPENAI_API_KEY=your_api_key_here`の形式でAPIキーを設定してください。")
                return
            
            # OpenAIクライアントを初期化
            if not report_generator.initialize_openai(openai_api_key):
                st.warning("💡 **OpenAI APIキーのトラブルシューティング:**")
                with st.expander("APIキーの確認・更新方法", expanded=True):
                    st.markdown("""
                **1. OpenAI Platform にアクセス:**
                - https://platform.openai.com/ にアクセス
                - アカウントにログイン
                
                **2. APIキーの確認:**
                - 左サイドバーの「API Keys」をクリック
                - 既存のキーが有効か確認（使用制限やクレジット残高も確認）
                
                **3. 新しいAPIキーの作成（必要に応じて）:**
                - 「Create new secret key」をクリック
                """)
                return
            
            # 複数店舗のレポート生成
            with st.spinner(f"📝 {len(output_stores)}店舗のレポートを生成中..."):
                for store_index, selected_store_name in enumerate(output_stores):
                    st.markdown(f"### 🏪 {selected_store_name}店のレポート")
                    
                    # 進捗表示
                    progress_text = f"店舗 {store_index + 1}/{len(output_stores)}: {selected_store_name}店"
                    progress_bar = st.progress((store_index) / len(output_stores), text=progress_text)
                    
                    # 現在選択中の店舗・週の追加情報を取得
                    current_monday_str = st.session_state['selected_monday']
                    topics_data = get_weekly_additional_data(selected_store_name, current_monday_str, 'topics') or ''
                    impact_day_data = get_weekly_additional_data(selected_store_name, current_monday_str, 'impact_day') or ''
                    quantitative_data_data = get_weekly_additional_data(selected_store_name, current_monday_str, 'quantitative_data') or ''
                    
                    data_for_ai = {
                        'daily_reports': {selected_store_name: st.session_state['daily_reports_input'][selected_store_name]},
                        'topics': topics_data,
                        'impact_day': impact_day_data,
                        'quantitative_data': quantitative_data_data
                    }
                    
                    # AI生成したレポートのキーを生成
                    ai_report_key = f"ai_generated_report_{selected_store_name}_{current_monday_str}"
                    
                    # レポート生成（常に最新データで再生成）
                    report_result = report_generator.generate_weekly_report(data_for_ai)
                    if report_result and isinstance(report_result, dict) and report_result.get('trend'):
                        # レポート結果を辞書として保存
                        st.session_state[ai_report_key] = report_result
                        # 週次出力データとして保存
                        set_weekly_report_output(selected_store_name, current_monday_str, 'generated_report', report_result)
                        
                        # 現在選択中の店舗の場合は、従来の表示用変数も更新
                        if selected_store_name == st.session_state.get('selected_store_for_report'):
                            st.session_state['generated_report_output'] = report_result
                        
                        # データベースにも最新のレポートを保存
                        store_id = db_manager.get_store_id_by_name(selected_store_name)
                        save_draft_data(
                            selected_store_name,
                            current_monday_str,
                            {selected_store_name: st.session_state['daily_reports_input'][selected_store_name]},
                            topics_data,
                            impact_day_data,
                            quantitative_data_data,
                            report_result  # 生成されたレポートも保存
                        )
                    else:
                        st.error(f"❌ {selected_store_name}店のレポート生成に失敗しました。")
                        continue
                    
                    # レポート表示
                    if ai_report_key in st.session_state:
                        report_data = st.session_state[ai_report_key]
                        # 辞書形式のレポートデータから表示用テキストを生成
                        if isinstance(report_data, dict):
                            display_text = report_data.get('trend', 'レポートデータが正しく生成されませんでした。')
                            factors = report_data.get('factors', [])
                            questions = report_data.get('questions', [])
                            
                            # 表示用のフォーマット済みテキストを作成
                            formatted_report = f"【週全体の動向】\n{display_text}\n\n"
                            if factors:
                                formatted_report += f"【主な要因】\n"
                                for i, factor in enumerate(factors, 1):
                                    formatted_report += f"{i}. {factor}\n"
                                formatted_report += "\n"
                            if questions:
                                formatted_report += f"【AIからの質問】\n"
                                for i, question in enumerate(questions, 1):
                                    formatted_report += f"{i}. {question}\n"
                        else:
                            # 文字列形式の場合（後方互換性）
                            formatted_report = str(report_data)
                        
                        with st.container():
                            st.text_area(
                                f"🤖 AI生成レポート ({selected_store_name}店)",
                                value=formatted_report,
                                height=300,
                                key=f"ai_report_display_{selected_store_name}_{current_monday_str}"
                            )
                            
                            # ダウンロードボタン
                            st.download_button(
                                label=f"📊 {selected_store_name}店レポートをダウンロード",
                                data=formatted_report,
                                file_name=f"weekly_report_{selected_store_name}_{current_monday_str}.txt",
                                mime="text/plain",
                                key=f"download_{selected_store_name}_{current_monday_str}"
                            )
                    
                    # 進捗更新
                    progress_bar.progress((store_index + 1) / len(output_stores), text=f"完了: {selected_store_name}店")
                    
                    if store_index < len(output_stores) - 1:
                        st.markdown("---")
                
                st.success(f"✅ {len(output_stores)}店舗のレポート生成が完了しました！")
                
        except Exception as e:
            st.error(f"❌ レポート生成中にエラーが発生しました: {str(e)}")
            st.exception(e)
    
    st.markdown("---")
    
    # 生成されたレポートの表示部分（現在選択中の店舗のレポートを表示）
    current_store_for_display = st.session_state.get('selected_store_for_report')
    current_monday_for_display = st.session_state.get('selected_monday')
    
    # 現在の店舗・週のレポートを優先して取得
    display_report = None
    if current_store_for_display and current_monday_for_display:
        display_report = get_weekly_report_output(current_store_for_display, current_monday_for_display, 'generated_report')
    
    # フォールバック: 従来のsession_stateからも取得
    if not display_report:
        display_report = st.session_state.get('generated_report_output')
    
    if display_report and isinstance(display_report, dict) and display_report.get('trend'):
        st.subheader(f"生成された週次レポート ({current_store_for_display}店 - AI生成)")
        
        # 整合性チェック結果を表示
        if 'consistency_check' in display_report:
            consistency_check = display_report['consistency_check']
            
            if not consistency_check['is_consistent'] or consistency_check['notes']:
                with st.expander("📊 定量データ整合性チェック結果", expanded=True):
                    if not consistency_check['is_consistent']:
                        st.warning("⚠️ **整合性の問題が検出されました:**")
                        for issue in consistency_check['issues']:
                            st.error(f"• {issue}")
                    
                    if consistency_check['notes']:
                        st.info("📝 **確認事項:**")
                        for note in consistency_check['notes']:
                            st.info(f"• {note}")
                    
                    st.markdown("---")
        
        st.markdown("**週全体の動向と要因:**")
        st.write(display_report.get('trend', ''))
        st.markdown("**主な要因:**")
        for i, factor in enumerate(display_report.get('factors', [])):
            st.write(f"- {factor}")
        
        if display_report.get('questions'):
            st.markdown("**AIからの質問:**")
            for q in display_report.get('questions', []):
                st.write(f"- {q}")
        
        # 従来の互換性のため、session_stateも更新
        st.session_state['generated_report_output'] = display_report

    st.markdown("---")

    # レポート修正エリア (生成済みレポートがある場合のみ表示)
    # 現在の店舗・週のレポートを確認
    current_store_report = None
    current_modified_report = None
    if current_store_for_display and current_monday_for_display:
        current_store_report = get_weekly_report_output(current_store_for_display, current_monday_for_display, 'generated_report')
        current_modified_report = get_weekly_report_output(current_store_for_display, current_monday_for_display, 'modified_report')
    
    # フォールバック
    if not current_store_report:
        current_store_report = st.session_state.get('generated_report_output')
    if not current_modified_report:
        current_modified_report = st.session_state.get('modified_report_output')
    
    if current_store_report or current_modified_report:
        st.header("5. レポートの修正と学習 (任意)")
        st.info("AIが生成したレポートを修正し、「修正して学習」ボタンを押すと、システムがその修正から学び、将来のレポート精度向上に役立てます。")

        report_to_display = current_modified_report if current_modified_report else current_store_report

        # 保存された修正内容がある場合はそれを使用、なければ元のレポート内容を使用
        default_trend = get_saved_modification('trend') or report_to_display.get('trend', '')
        default_factors = get_saved_modification('factors') or ", ".join(report_to_display.get('factors', []))
        default_questions = get_saved_modification('questions') or "\n".join(report_to_display.get('questions', []))
        default_edit_reason = get_saved_modification('edit_reason')

        modified_trend = st.text_area(
            "**修正後の週全体の動向と要因:**",
            value=default_trend,
            key="modified_trend_input",
            height=200,
            on_change=auto_save_modification
        )
        modified_factors_str = st.text_input(
            "**修正後の主な要因 (カンマ区切り):**",
            value=default_factors,
            key="modified_factors_input",
            on_change=auto_save_modification
        )
        modified_questions_str = st.text_area(
            "**修正後のAIへの質問:**",
            value=default_questions,
            key="modified_questions_input",
            height=100,
            on_change=auto_save_modification
        )
        edit_reason = st.text_area(
            "**修正理由 (学習のために重要です):** 何を、なぜ修正したのかを具体的に記述してください。",
            value=default_edit_reason,
            key="edit_reason_input",
            height=100,
            on_change=auto_save_modification
        )
        
        modified_factors = [f.strip() for f in modified_factors_str.split(',') if f.strip()]
        modified_questions = [q.strip() for q in modified_questions_str.split('\n') if q.strip()]

        if st.button("修正して学習", type="primary", key="learn_from_correction_button"):
            if not edit_reason.strip():
                st.error("修正理由を入力してください。これはAIの学習に不可欠です。")
            else:
                modified_report_data = {
                    "trend": modified_trend,
                    "factors": modified_factors,
                    "questions": modified_questions,
                    "edit_reason": edit_reason
                }
                st.session_state['modified_report_output'] = modified_report_data

                # 新しいデータ構造にも保存
                current_store_name = st.session_state['selected_store_for_report']
                current_monday = st.session_state['selected_monday']
                set_weekly_report_output(current_store_name, current_monday, 'modified_report', modified_report_data)

                store_id = db_manager.get_store_id_by_name(st.session_state['selected_store_for_report'])
                monday_date_str = st.session_state['selected_monday']
                current_store_name = st.session_state['selected_store_for_report']
                
                # session_stateのデータ構造を確保
                if 'daily_reports_input' not in st.session_state:
                    st.session_state['daily_reports_input'] = {}
                if current_store_name not in st.session_state['daily_reports_input']:
                    st.session_state['daily_reports_input'][current_store_name] = {}
                
                # 現在選択中の店舗・週の追加情報を取得
                topics_for_learning = get_weekly_additional_data(current_store_name, monday_date_str, 'topics') or st.session_state.get('topics_input', '')
                impact_day_for_learning = get_weekly_additional_data(current_store_name, monday_date_str, 'impact_day') or st.session_state.get('impact_day_input', '')
                quantitative_data_for_learning = get_weekly_additional_data(current_store_name, monday_date_str, 'quantitative_data') or st.session_state.get('quantitative_data_input', '')
                
                input_data_for_learning = {
                    'daily_reports': {current_store_name: st.session_state['daily_reports_input'][current_store_name]},
                    'topics': topics_for_learning,
                    'impact_day': impact_day_for_learning,
                    'quantitative_data': quantitative_data_for_learning
                }

                # DBに保存し、学習エンジンに渡す
                is_updated = db_manager.save_weekly_data(
                    store_id,
                    monday_date_str,
                    input_data_for_learning, # daily_reports_inputを直接渡す
                    st.session_state['generated_report_output'],
                    modified_report_data
                )
                
                learning_engine.learn_from_correction(
                    input_data=input_data_for_learning,
                    original_output=st.session_state['generated_report_output'],
                    modified_output=modified_report_data
                )
                
                # 修正内容の保存データをクリア
                clear_saved_modifications()
                
                if is_updated:
                    st.success("✅ 修正内容が保存され、システムが学習しました！（データ更新）")
                else:
                    st.success("✅ 修正内容が保存され、システムが学習しました！（新規保存）")
                st.rerun()


def show_report_history_page():
    st.title("📚 レポート履歴")
    st.markdown("---")

    st.info("ここでは、これまでに作成・保存された週次レポートの一覧を確認できます。")

    all_stores = db_manager.get_all_stores()
    store_names = [s[1] for s in all_stores]
    store_id_map = {s[1]: s[0] for s in all_stores}

    selected_store_name = st.selectbox("表示する店舗を選択:", ["全店舗"] + store_names)

    if selected_store_name == "全店舗":
        reports = db_manager.get_all_weekly_reports()
    else:
        selected_store_id = store_id_map[selected_store_name]
        reports = db_manager.get_all_weekly_reports(selected_store_id)

    if not reports:
        st.warning("表示するレポートがありません。")
        return

    report_data = []
    for r in reports:
        # store_name は既に DBManager で追加されているはず
        try:
            store_name = db_manager.get_store_name_by_id(r['store_id'])
        except Exception as e:
            store_name = f"店舗ID:{r['store_id']}"
            
        report_data.append({
            "ID": r['id'],
            "店舗名": store_name,
            "週次レポート (月曜日)": r['monday_date'],
            "最終更新日時": datetime.fromisoformat(r['timestamp']).strftime('%Y/%m/%d %H:%M'),
            "AI生成済み": "はい" if r['has_generated'] else "いいえ",
            "修正済み": "はい" if r['has_modified'] else "いいえ",
            "ダウンロード": f"Download_{r['id']}" # ダミーの列名
        })
    
    df = pd.DataFrame(report_data)

    st.dataframe(df.set_index('ID'), use_container_width=True)

    # レポート詳細表示・ダウンロード
    st.subheader("レポートの詳細表示とダウンロード")
    report_ids = [r['id'] for r in reports]
    
    if report_ids:
        selected_report_id = st.selectbox("詳細を表示・ダウンロードするレポートのIDを選択してください:", report_ids)

        if selected_report_id:
            # IDの型を確認・修正（必要に応じて整数に変換）
            try:
                selected_report_id = int(selected_report_id)
            except (ValueError, TypeError):
                pass  # すでに適切な型の場合はそのまま
                
            # 選択されたレポートIDが実際にリストに存在するかチェック
            if selected_report_id not in report_ids:
                st.error(f"選択されたレポートID {selected_report_id} は存在しません。")
                return
                
            selected_report_db = next((r for r in reports if r['id'] == selected_report_id), None)
            
            if not selected_report_db:
                st.error(f"レポートID {selected_report_id} の情報を取得できませんでした。")
                return
                
            # DBから最新の完全なレポートデータを再取得
            try:
                full_report = db_manager.get_weekly_report(selected_report_db['store_id'], selected_report_db['monday_date'])
                
                if not full_report:
                    st.error(f"レポートID {selected_report_id} のデータを取得できませんでした。")
                    return
                    
            except Exception as e:
                st.error(f"レポート取得中にエラーが発生しました: {str(e)}")
                return
                
            if full_report:
                st.markdown(f"### レポートID: {full_report['id']} - {db_manager.get_store_name_by_id(full_report['store_id'])}店 - 週次: {full_report['monday_date']}")
                st.write(f"最終更新日時: {datetime.fromisoformat(full_report['timestamp']).strftime('%Y/%m/%d %H:%M')}")

                # ダウンロード用のデータ整形（エラーハンドリング強化）
                export_data = {
                    "レポート対象週の月曜日": full_report.get('monday_date', ''),
                    "店舗名": db_manager.get_store_name_by_id(full_report.get('store_id', 0)),
                    "TOPICS": full_report.get('topics', ''),
                    "インパクト大": full_report.get('impact_day', ''),
                    "定量データ": full_report.get('quantitative_data', '')
                }
                
                # 生成レポートデータの安全な取得
                generated_report = full_report.get('generated_report', {})
                if isinstance(generated_report, dict):
                    export_data.update({
                        "AI生成レポート_動向": generated_report.get('trend', ''),
                        "AI生成レポート_要因": ", ".join(generated_report.get('factors', [])) if generated_report.get('factors') else '',
                        "AI生成レポート_質問": "\n".join(generated_report.get('questions', [])) if generated_report.get('questions') else ''
                    })
                
                # 修正レポートデータの安全な取得
                modified_report = full_report.get('modified_report')
                if isinstance(modified_report, dict):
                    export_data.update({
                        "修正後レポート_動向": modified_report.get('trend', ''),
                        "修正後レポート_要因": ", ".join(modified_report.get('factors', [])) if modified_report.get('factors') else '',
                        "修正後レポート_質問": "\n".join(modified_report.get('questions', [])) if modified_report.get('questions') else '',
                        "修正理由": modified_report.get('edit_reason', '')
                    })
                
                # 日次レポートの詳細を安全に追加
                daily_reports = full_report.get('daily_reports', {})
                if isinstance(daily_reports, dict):
                    for store_name, dates_data in daily_reports.items():
                        if isinstance(dates_data, dict):
                            for date_str, report_data in dates_data.items():
                                try:
                                    if isinstance(report_data, dict):
                                        export_data[f"日次動向_{store_name}_{date_str}"] = str(report_data.get('trend', ''))
                                        factors = report_data.get('factors', [])
                                        export_data[f"日次要因_{store_name}_{date_str}"] = ", ".join(factors) if isinstance(factors, list) else str(factors)
                                    else:
                                        export_data[f"日次動向_{store_name}_{date_str}"] = ''
                                        export_data[f"日次要因_{store_name}_{date_str}"] = ''
                                except Exception as e:
                                    print(f"日次データ処理エラー: {e}")
                                    export_data[f"日次動向_{store_name}_{date_str}"] = ''
                                    export_data[f"日次要因_{store_name}_{date_str}"] = ''

                df_export = pd.DataFrame([export_data])
                
                # Excelダウンロード（エラーハンドリング付き）
                try:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_export.to_excel(writer, index=False, sheet_name='レポート')
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="📊 レポートをExcelでダウンロード",
                        data=excel_data,
                        file_name=f"週次レポート_{full_report['monday_date']}_{db_manager.get_store_name_by_id(full_report['store_id'])}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except ImportError:
                    st.warning("⚠️ Excel形式でのダウンロードができません。CSV形式でダウンロードしてください。")
                    # CSVダウンロードをフォールバックとして提供
                    csv_data = df_export.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📄 レポートをCSVでダウンロード",
                        data=csv_data,
                        file_name=f"週次レポート_{full_report['monday_date']}_{db_manager.get_store_name_by_id(full_report['store_id'])}.csv",
                        mime="text/csv"
                    )

                st.markdown("#### レポート内容プレビュー")
                
                # 修正レポートの表示
                modified_report = full_report.get('modified_report')
                if modified_report and isinstance(modified_report, dict):
                    st.subheader("--- 最終修正版レポート ---")
                    st.markdown("**週全体の動向と要因:**")
                    st.write(modified_report.get('trend', ''))
                    st.markdown("**主な要因:**")
                    factors = modified_report.get('factors', [])
                    if isinstance(factors, list):
                        for factor in factors:
                            st.write(f"- {factor}")
                    
                    questions = modified_report.get('questions', [])
                    if questions and isinstance(questions, list):
                        st.markdown("**AIへの質問:**")
                        for q in questions:
                                st.write(f"- {q}")
                    
                    edit_reason = modified_report.get('edit_reason')
                    if edit_reason:
                        st.markdown("**修正理由:**")
                        st.write(edit_reason)
                
                # 生成レポートの表示
                generated_report = full_report.get('generated_report')
                if generated_report and isinstance(generated_report, dict):
                    st.subheader("--- AI生成レポート (オリジナル) ---")
                    st.markdown("**週全体の動向と要因:**")
                    st.write(generated_report.get('trend', ''))
                    st.markdown("**主な要因:**")
                    factors = generated_report.get('factors', [])
                    if isinstance(factors, list):
                        for factor in factors:
                            st.write(f"- {factor}")
                    
                    questions = generated_report.get('questions', [])
                    if questions and isinstance(questions, list):
                        st.markdown("**AIからの質問:**")
                        for q in questions:
                            st.write(f"- {q}")
                
                st.subheader("--- 入力データ ---")
                st.markdown("**日次レポート:**")
                daily_reports = full_report.get('daily_reports', {})
                if daily_reports and isinstance(daily_reports, dict):
                    # 単一店舗のレポートの場合（正しい構造）
                    if all(key.count('-') == 2 and len(key) == 10 for key in daily_reports.keys() if isinstance(key, str)):
                        store_name = db_manager.get_store_name_by_id(full_report.get('store_id', 0))
                        st.markdown(f"**{store_name}店**")
                        has_data = False
                        for date_str, report_data in daily_reports.items():
                            try:
                                if isinstance(report_data, dict):
                                    trend_text = report_data.get('trend', '').strip()
                                    factors_list = report_data.get('factors', [])
                                    
                                    # 動向または要因のいずれかにデータがある場合のみ表示
                                    if trend_text or (factors_list and len(factors_list) > 0):
                                        has_data = True
                                        if isinstance(factors_list, list):
                                            factors_text = ', '.join(factors_list) if factors_list else '要因なし'
                                        else:
                                            factors_text = str(factors_list) if factors_list else '要因なし'
                                        
                                        st.markdown(f"  - **{date_str}**")
                                        if trend_text:
                                            st.markdown(f"    動向: {trend_text}")
                                        if factors_list:
                                            st.markdown(f"    要因: {factors_text}")
                                        else:
                                            st.markdown(f"    要因: 要因なし")
                                else:
                                    st.markdown(f"  - {date_str} データ形式エラー")
                            except Exception as e:
                                st.markdown(f"  - {date_str} データ読み込みエラー")
                        
                        if not has_data:
                            st.markdown("  - この店舗には入力済みの日次データがありません")
                    else:
                        # 複数店舗データが混在している場合（古い構造）
                        for store_key, dates_data in daily_reports.items():
                            # 店舗名のキーのみ処理
                            if not (isinstance(store_key, str) and len(store_key) == 10 and store_key.count('-') == 2):
                                st.markdown(f"**{store_key}店**")
                                if isinstance(dates_data, dict):
                                    has_data = False
                                    for date_str, report_data in dates_data.items():
                                        try:
                                            if isinstance(report_data, dict):
                                                trend_text = report_data.get('trend', '').strip()
                                                factors_list = report_data.get('factors', [])
                                                
                                                # 動向または要因のいずれかにデータがある場合のみ表示
                                                if trend_text or (factors_list and len(factors_list) > 0):
                                                    has_data = True
                                                    if isinstance(factors_list, list):
                                                        factors_text = ', '.join(factors_list) if factors_list else '要因なし'
                                                    else:
                                                        factors_text = str(factors_list) if factors_list else '要因なし'
                                                    
                                                    st.markdown(f"  - **{date_str}**")
                                                    if trend_text:
                                                        st.markdown(f"    動向: {trend_text}")
                                                    if factors_list:
                                                        st.markdown(f"    要因: {factors_text}")
                                                    else:
                                                        st.markdown(f"    要因: 要因なし")
                                            else:
                                                st.markdown(f"  - {date_str} データ形式エラー")
                                        except Exception as e:
                                            st.markdown(f"  - {date_str} データ読み込みエラー")
                                    
                                    if not has_data:
                                        st.markdown("  - この店舗には入力済みの日次データがありません")
                                else:
                                    st.markdown("  - データ構造エラー")
                else:
                    st.markdown("日次レポートデータがありません。")

                st.markdown("**TOPICS:**")
                st.write(full_report.get('topics', 'N/A'))
                st.markdown("**インパクト大:**")
                st.write(full_report.get('impact_day', 'N/A'))
                st.markdown("**定量データ:**")
                st.write(full_report.get('quantitative_data', 'N/A'))
            else:
                st.warning("選択されたレポートの詳細を読み込めませんでした。")
    else:
        st.info("レポート履歴がありません。")

def show_settings_page():
    st.title("⚙️ 設定")
    st.markdown("---")

    st.subheader("OpenAI APIキー設定")
    
    # 環境変数から現在のAPIキーの設定状況を確認
    current_api_key = os.getenv("OPENAI_API_KEY", "")
    
    if current_api_key:
        st.success("✅ OpenAI APIキーが設定されています。")
        st.info("APIキーは環境変数から読み込まれています。変更が必要な場合は、システム管理者にお問い合わせください。")
    else:
        st.error("❌ OpenAI APIキーが設定されていません。")
        st.warning("システム管理者にOpenAI APIキーの設定を依頼してください。")
        st.markdown("""
        **管理者向け設定手順:**
        1. `.env`ファイルを作成または編集
        2. `OPENAI_API_KEY=your_api_key_here` の形式でAPIキーを設定
        3. アプリケーションを再起動
        """)

    st.markdown("---")

    st.subheader("学習データ管理 (開発中)")
    st.info("AIの精度向上に使用される学習データを管理します。")

    try:
        learning_stats = db_manager.get_learning_stats()
        st.write(f"登録されているレポート数: **{learning_stats['total_reports']}**")
        st.write(f"ユーザー修正済みレポート数: **{learning_stats['corrections']}**")
        st.write(f"学習パターン数: **{learning_stats['patterns']}**")
    except Exception as e:
        st.error(f"学習データの読み込みでエラーが発生しました: {str(e)}")
        st.info("データベースの初期化が必要な可能性があります。")

    # 学習データのエクスポート機能 (例)
    st.markdown("---")
    st.subheader("学習データのエクスポート")
    if st.button("全学習データをダウンロード (開発者向け)"):
        # 仮の学習データ取得ロジック（実際にはlearning_patternsテーブルから取得）
        conn = db_manager._get_connection()
        learning_data_df = pd.read_sql_query("SELECT * FROM learning_patterns", conn)
        conn.close()

        if not learning_data_df.empty:
            st.download_button(
                label="学習データをCSVでダウンロード",
                data=learning_data_df.to_csv(index=False, encoding='utf-8-sig'),
                file_name="learning_data_export.csv",
                mime="text/csv"
            )
            st.success("学習データをダウンロードしました。")
        else:
            st.warning("ダウンロードする学習データがありません。")


# メインナビゲーション
st.sidebar.title("ナビゲーション")

selection = st.sidebar.radio("Go to", ["週次レポート作成", "レポート履歴", "設定"])

if selection == "週次レポート作成":
    show_report_creation_page()
elif selection == "レポート履歴":
    show_report_history_page()
elif selection == "設定":
    show_settings_page()