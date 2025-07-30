"""
マルチデバイス対応機能
複数のデバイス・PCから同時にレポート編集を可能にする機能群
"""
import sqlite3
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import streamlit as st

class MultiDeviceManager:
    """複数デバイス間でのデータ同期を管理するクラス"""
    
    def __init__(self, db_path: str = 'apparel_reports.db'):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_sync_tables()
    
    def _init_sync_tables(self):
        """同期用のテーブルを初期化"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # デバイス・セッション管理テーブル
            conn.execute('''
                CREATE TABLE IF NOT EXISTS active_sessions (
                    session_id TEXT PRIMARY KEY,
                    device_info TEXT,
                    store_name TEXT,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    editing_data TEXT
                )
            ''')
            
            # リアルタイム同期用データテーブル
            conn.execute('''
                CREATE TABLE IF NOT EXISTS realtime_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_name TEXT NOT NULL,
                    monday_date TEXT NOT NULL,
                    field_type TEXT NOT NULL,  -- daily_trend, daily_factors, topics, impact_day, quantitative
                    field_key TEXT,  -- 日付やフィールド名
                    field_value TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_id TEXT,
                    UNIQUE(store_name, monday_date, field_type, field_key)
                )
            ''')
            
            # 編集ロック管理テーブル
            conn.execute('''
                CREATE TABLE IF NOT EXISTS edit_locks (
                    store_name TEXT NOT NULL,
                    monday_date TEXT NOT NULL,
                    field_type TEXT NOT NULL,
                    field_key TEXT,
                    session_id TEXT NOT NULL,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (store_name, monday_date, field_type, field_key)
                )
            ''')
            
            conn.commit()
    
    def register_session(self, store_name: str, device_info: str = "") -> str:
        """デバイス・セッションを登録"""
        session_id = f"session_{int(time.time() * 1000)}_{hash(device_info) % 10000}"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO active_sessions 
                (session_id, device_info, store_name, last_active)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (session_id, device_info, store_name))
            conn.commit()
        
        return session_id
    
    def update_realtime_data(self, session_id: str, store_name: str, monday_date: str, 
                           field_type: str, field_key: str, field_value: str):
        """リアルタイムデータを更新"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO realtime_data 
                    (store_name, monday_date, field_type, field_key, field_value, session_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (store_name, monday_date, field_type, field_key, field_value, session_id))
                conn.commit()
    
    def get_latest_data(self, store_name: str, monday_date: str, exclude_session: str = None) -> Dict:
        """最新のデータを取得（自分のセッション以外から）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = '''
                SELECT field_type, field_key, field_value, last_updated, session_id
                FROM realtime_data 
                WHERE store_name = ? AND monday_date = ?
            '''
            params = [store_name, monday_date]
            
            if exclude_session:
                query += ' AND session_id != ?'
                params.append(exclude_session)
                
            query += ' ORDER BY last_updated DESC'
            
            rows = conn.execute(query, params).fetchall()
            
            result = {}
            for row in rows:
                field_type = row['field_type']
                if field_type not in result:
                    result[field_type] = {}
                
                result[field_type][row['field_key']] = {
                    'value': row['field_value'],
                    'updated': row['last_updated'],
                    'session': row['session_id']
                }
            
            return result
    
    def get_active_sessions(self, store_name: str) -> List[Dict]:
        """指定店舗でアクティブなセッション一覧を取得"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # 5分以内にアクティビティがあるセッションを取得
            cutoff_time = datetime.now() - timedelta(minutes=5)
            
            rows = conn.execute('''
                SELECT session_id, device_info, last_active
                FROM active_sessions 
                WHERE store_name = ? AND last_active > ?
                ORDER BY last_active DESC
            ''', (store_name, cutoff_time.isoformat())).fetchall()
            
            return [dict(row) for row in rows]
    
    def cleanup_inactive_sessions(self):
        """非アクティブなセッションをクリーンアップ"""
        cutoff_time = datetime.now() - timedelta(minutes=30)
        
        with sqlite3.connect(self.db_path) as conn:
            # 古いセッションを削除
            conn.execute('''
                DELETE FROM active_sessions 
                WHERE last_active < ?
            ''', (cutoff_time.isoformat(),))
            
            # 古いリアルタイムデータを削除（1週間以上古い）
            week_ago = datetime.now() - timedelta(weeks=1)
            conn.execute('''
                DELETE FROM realtime_data 
                WHERE last_updated < ?
            ''', (week_ago.isoformat(),))
            
            conn.commit()

def init_multi_device_session(store_name: str) -> str:
    """マルチデバイスセッションを初期化"""
    if 'multi_device_manager' not in st.session_state:
        st.session_state['multi_device_manager'] = MultiDeviceManager()
    
    if 'device_session_id' not in st.session_state:
        # デバイス情報を生成
        import platform
        device_info = f"{platform.system()}_{platform.node()}_{int(time.time())}"
        st.session_state['device_session_id'] = st.session_state['multi_device_manager'].register_session(
            store_name, device_info
        )
    
    return st.session_state['device_session_id']

def sync_field_update(store_name: str, monday_date: str, field_type: str, 
                     field_key: str, field_value: str):
    """フィールド更新を他のデバイスと同期"""
    if 'multi_device_manager' in st.session_state and 'device_session_id' in st.session_state:
        st.session_state['multi_device_manager'].update_realtime_data(
            st.session_state['device_session_id'],
            store_name, monday_date, field_type, field_key, field_value
        )

def get_sync_updates(store_name: str, monday_date: str) -> Dict:
    """他のデバイスからの更新を取得"""
    if 'multi_device_manager' in st.session_state and 'device_session_id' in st.session_state:
        return st.session_state['multi_device_manager'].get_latest_data(
            store_name, monday_date, st.session_state['device_session_id']
        )
    return {}

def show_active_devices(store_name: str):
    """現在アクティブなデバイス一覧を表示"""
    if 'multi_device_manager' in st.session_state:
        sessions = st.session_state['multi_device_manager'].get_active_sessions(store_name)
        
        if len(sessions) > 1:
            st.info(f"🔄 **{store_name}店で{len(sessions)}台のデバイスが編集中**")
            with st.expander("アクティブなデバイス", key=f"devices_{store_name}"):
                for i, session in enumerate(sessions):
                    device_short = session['session_id'][-8:]
                    last_active = session['last_active']
                    st.write(f"📱 デバイス {device_short} - 最終更新: {last_active}")
        else:
            st.success(f"✅ **{store_name}店 - 単独編集中**")

def auto_refresh_data(store_name: str = None, context: str = "default"):
    """定期的にデータを更新"""
    import random
    
    # 店舗名、コンテキスト、セッションID、ランダム要素を含めた完全にユニークなキーを生成
    session_suffix = ""
    if 'device_session_id' in st.session_state:
        session_suffix = f"_{st.session_state['device_session_id'][-6:]}"
    
    # ランダム要素とタイムスタンプを追加してさらに一意性を保証
    random_suffix = f"_{random.randint(1000, 9999)}"
    timestamp_suffix = f"_{int(time.time() * 1000) % 100000}"
    
    key_suffix = f"_{store_name}_{context}{session_suffix}{random_suffix}{timestamp_suffix}" if store_name else f"_{context}{session_suffix}{random_suffix}{timestamp_suffix}"
    button_key = f"refresh_sync_data{key_suffix}"
    
    if st.button("🔄 最新データを同期", key=button_key):
        st.rerun()
