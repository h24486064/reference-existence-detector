#!/usr/bin/env python
"""
GUI版本的PDF參考文獻驗證工具
使用tkinter創建簡單的圖形界面
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
import time
import pandas as pd
from pathlib import Path

# 導入原有的模組，但需要修改API_KEY的處理方式
import document_processor
import crossref_client
import matcher

class PDFVerifierGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("參考文獻驗證工具")
        self.root.geometry("800x700")
        self.root.resizable(True, True)
        
        # 設定字體
        self.font_default = ("Microsoft YaHei", 10)
        self.font_title = ("Microsoft YaHei", 12, "bold")
        
        # 變數
        self.pdf_path = tk.StringVar()
        self.api_key = tk.StringVar()
        self.output_path = tk.StringVar()
        self.processing = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """建立使用者界面"""
        
        # 主標題
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill=tk.X, padx=20, pady=10)
        
        title_label = ttk.Label(title_frame, text="PDF 參考文獻驗證工具", font=self.font_title)
        title_label.pack()
        
        # API Key 輸入區域
        api_frame = ttk.LabelFrame(self.root, text="Gemini API Key 設定", padding=10)
        api_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(api_frame, text="請輸入您的 Gemini API Key:", font=self.font_default).pack(anchor=tk.W)
        
        api_entry_frame = ttk.Frame(api_frame)
        api_entry_frame.pack(fill=tk.X, pady=5)
        
        self.api_entry = ttk.Entry(api_entry_frame, textvariable=self.api_key, show="*", font=self.font_default)
        self.api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        show_api_btn = ttk.Button(api_entry_frame, text="顯示/隱藏", command=self.toggle_api_visibility)
        show_api_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # PDF 檔案選擇區域
        pdf_frame = ttk.LabelFrame(self.root, text="PDF 檔案選擇", padding=10)
        pdf_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(pdf_frame, text="選擇要處理的 PDF 檔案:", font=self.font_default).pack(anchor=tk.W)
        
        pdf_select_frame = ttk.Frame(pdf_frame)
        pdf_select_frame.pack(fill=tk.X, pady=5)
        
        self.pdf_entry = ttk.Entry(pdf_select_frame, textvariable=self.pdf_path, font=self.font_default)
        self.pdf_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        pdf_browse_btn = ttk.Button(pdf_select_frame, text="瀏覽", command=self.browse_pdf)
        pdf_browse_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 輸出路徑選擇區域
        output_frame = ttk.LabelFrame(self.root, text="輸出設定", padding=10)
        output_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(output_frame, text="結果輸出路徑:", font=self.font_default).pack(anchor=tk.W)
        
        output_select_frame = ttk.Frame(output_frame)
        output_select_frame.pack(fill=tk.X, pady=5)
        
        self.output_entry = ttk.Entry(output_select_frame, textvariable=self.output_path, font=self.font_default)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        output_browse_btn = ttk.Button(output_select_frame, text="瀏覽", command=self.browse_output)
        output_browse_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 控制按鈕區域
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.start_btn = ttk.Button(control_frame, text="開始處理", command=self.start_processing, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT)
        
        self.stop_btn = ttk.Button(control_frame, text="停止", command=self.stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        clear_btn = ttk.Button(control_frame, text="清除記錄", command=self.clear_log)
        clear_btn.pack(side=tk.RIGHT)
        
        # 進度條
        self.progress = ttk.Progressbar(self.root, mode='indeterminate')
        self.progress.pack(fill=tk.X, padx=20, pady=5)
        
        # 記錄輸出區域
        log_frame = ttk.LabelFrame(self.root, text="處理記錄", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 狀態列
        self.status_var = tk.StringVar()
        self.status_var.set("準備就緒")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
    def toggle_api_visibility(self):
        """切換API Key的顯示/隱藏"""
        if self.api_entry['show'] == '*':
            self.api_entry.config(show='')
        else:
            self.api_entry.config(show='*')
    
    def browse_pdf(self):
        """瀏覽選擇PDF檔案"""
        filename = filedialog.askopenfilename(
            title="選擇 PDF 檔案",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if filename:
            self.pdf_path.set(filename)
    
    def browse_output(self):
        """瀏覽選擇輸出檔案"""
        # 根據已選擇的 PDF 檔案生成建議檔名
        suggested_filename = "result.csv"
        if self.pdf_path.get():
            pdf_basename = os.path.splitext(os.path.basename(self.pdf_path.get()))[0]
            suggested_filename = f"result_{pdf_basename}.csv"
        
        filename = filedialog.asksaveasfilename(
            title="選擇輸出檔案",
            initialfile=suggested_filename,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.output_path.set(filename)
    
    def log_message(self, message):
        """在記錄區域添加訊息"""
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def clear_log(self):
        """清除記錄"""
        self.log_text.delete(1.0, tk.END)
    
    def validate_inputs(self):
        """驗證輸入參數"""
        if not self.api_key.get().strip():
            messagebox.showerror("錯誤", "請輸入 Gemini API Key")
            return False
        
        if not self.pdf_path.get().strip():
            messagebox.showerror("錯誤", "請選擇要處理的 PDF 檔案")
            return False
        
        if not os.path.exists(self.pdf_path.get()):
            messagebox.showerror("錯誤", "選擇的 PDF 檔案不存在")
            return False
        
        if not self.output_path.get().strip():
            messagebox.showerror("錯誤", "請設定輸出檔案路徑")
            return False
        
        return True
    
    def start_processing(self):
        """開始處理"""
        if not self.validate_inputs():
            return
        
        if self.processing:
            return
        
        self.processing = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start()
        self.status_var.set("處理中...")
        
        # 在新線程中執行處理
        self.process_thread = threading.Thread(target=self.process_pdf, daemon=True)
        self.process_thread.start()
    
    def stop_processing(self):
        """停止處理"""
        self.processing = False
        self.progress.stop()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("已停止")
        self.log_message("處理已被使用者停止")
    
    def process_pdf(self):
        """處理PDF的主要邏輯"""
        try:
            # 設定API key到各個模組
            self.setup_api_key()
            
            # 開始處理
            self.log_message("="*50)
            self.log_message("開始處理 PDF 檔案")
            self.log_message(f"PDF 檔案: {self.pdf_path.get()}")
            self.log_message(f"輸出檔案: {self.output_path.get()}")
            
            # 執行主要處理邏輯（修改後的verify_refs邏輯）
            result = self.run_verification()
            
            if result and not self.processing:
                return  # 使用者停止了處理
            
            self.log_message("處理完成！")
            self.status_var.set("處理完成")
            
            # 顯示完成對話框
            self.root.after(0, lambda: messagebox.showinfo("完成", f"處理完成！\n結果已儲存至: {self.output_path.get()}"))
            
        except Exception as e:
            self.log_message(f"處理時發生錯誤: {str(e)}")
            self.status_var.set("處理失敗")
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"處理時發生錯誤:\n{str(e)}"))
        
        finally:
            self.processing = False
            self.progress.stop()
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            if self.status_var.get() == "處理中...":
                self.status_var.set("準備就緒")
    
    def setup_api_key(self):
        """設定API key到各個需要的模組"""
        api_key = self.api_key.get().strip()
        
        # 動態導入並設定API key
        import reference_extractor_gui
        import gemini_search_client_gui
        
        reference_extractor_gui.set_api_key(api_key)
        gemini_search_client_gui.set_api_key(api_key)
        
        self.log_message("API Key 設定完成")
    
    def run_verification(self):
        """執行驗證邏輯（修改自verify_refs.py）"""
        try:
            pdf_path = self.pdf_path.get()
            out_csv = self.output_path.get()
            
            if not self.processing:
                return False
            
            self.log_message(f"開始處理 PDF: {pdf_path}")
            
            # 調用PDF處理
            full_txt = document_processor.pdf_to_text(pdf_path)
            refs_txt = document_processor.extract_ref_block(full_txt)
            
            if not refs_txt.strip():
                self.log_message("錯誤：未能萃取出參考文獻區塊，程式終止。")
                return False
            
            self.log_message("成功萃取參考文獻文字。")
            
            if not self.processing:
                return False
            
            # 使用修改後的reference_extractor
            self.log_message("正在解析參考文獻...")
            import reference_extractor_gui
            raw_refs, _ = reference_extractor_gui.parse_references_with_gemini(refs_txt)
            
            if not raw_refs:
                self.log_message("未能解析出任何參考文獻，程式終止。")
                return False
            
            self.log_message(f"Gemini 解析成功 {len(raw_refs)} 條初步結果。")
            
            if not self.processing:
                return False
            
            # 標準化處理
            from utils import canonicalize_refs
            canon_refs = canonicalize_refs(raw_refs)
            self.log_message(f"標準化完成，共得到 {len(canon_refs)} 條唯一參考文獻。")
            
            for r in canon_refs:
                r["author"] = r["authors"][0] if r.get("authors") else "?"
            
            if not self.processing:
                return False
            
            # CrossRef API 查詢
            self.log_message("\n--- 階段一: 開始批次 CrossRef 查詢 ---")
            crossref_results = []
            
            for index, ref_item in enumerate(canon_refs):
                if not self.processing:
                    return False
                
                self.log_message(f"  [CrossRef] 正在查詢第 {index + 1} / {len(canon_refs)} 筆")
                crossref_results.append({**ref_item, **crossref_client.lookup(ref_item)})
                time.sleep(0.5)
            
            found_count = sum(1 for r in crossref_results if r.get('found') == 1)
            failed_count = len(crossref_results) - found_count
            self.log_message(f"CrossRef 階段完成。成功找到 {found_count} 筆，失敗 {failed_count} 筆。")
            
            if not self.processing:
                return False
            
            # Gemini Search 後備查詢
            if failed_count == 0:
                self.log_message("\n所有文獻已透過 CrossRef 成功找到，不啟用Gemini Search。")
                enriched_records = crossref_results
            else:
                self.log_message(f"\n--- 階段二: 針對 {failed_count} 筆失敗項目，開始 Gemini Search 後備查詢 ---")
                
                final_results_map = {(r.get('authors')[0] if r.get('authors') else '?', r.get('year')): r for r in crossref_results}
                refs_for_gemini = [r for r in crossref_results if r.get('found') == 0]
                
                import gemini_search_client_gui
                gemini_found_count = 0
                
                for index, ref_item in enumerate(refs_for_gemini):
                    if not self.processing:
                        return False
                    
                    title_preview = str(ref_item.get('title', 'N/A'))[:60]
                    self.log_message(f"  [Gemini] 正在查詢第 {index + 1} / {len(refs_for_gemini)} 筆: {title_preview}")
                    
                    gemini_search_result = gemini_search_client_gui.find_reference_with_gemini_search(ref_item)
                    
                    if gemini_search_result.get("found") == 1:
                        gemini_found_count += 1
                        original_key = (ref_item.get('authors')[0] if ref_item.get('authors') else '?', ref_item.get('year'))
                        final_results_map[original_key].update(gemini_search_result)
                        self.log_message(f"    -> Gemini 找到 DOI: {gemini_search_result.get('cr_doi')}")
                    else:
                        self.log_message("    -> 失敗。Gemini 未能找到明確結果。")
                    
                    time.sleep(1)
                
                self.log_message(f"Gemini 後備查詢階段完成。額外成功找到 {gemini_found_count} 筆。")
                enriched_records = list(final_results_map.values())
            
            if not self.processing:
                return False
            
            # 輸出結果
            df_final = pd.DataFrame(enriched_records)
            df_final['author'] = df_final['authors'].apply(lambda authors: authors[0] if isinstance(authors, list) and authors else "?")
            
            desired_order = ['author', 'year', 'title', 'doi', 'found', 'cr_title', 'cr_doi', 'verification_url', 'raw']
            
            for col in desired_order:
                if col not in df_final.columns:
                    df_final[col] = ""
            
            df_final['verification_url'] = df_final['verification_url'].fillna('')
            df_final = df_final[desired_order]
            
            df_final.to_csv(out_csv, index=False, encoding="utf-8-sig")
            
            final_success_count = sum(1 for r in df_final.to_dict('records') if r.get('found') == 1)
            self.log_message(f"\n查找流程完成")
            self.log_message(f"成功匹配 {final_success_count} / {len(canon_refs)} 筆參考文獻。")
            self.log_message(f"結果儲存至 {out_csv}")
            
            return True
            
        except Exception as e:
            self.log_message(f"處理過程中發生錯誤: {str(e)}")
            return False


def main():
    """主程式入口"""
    root = tk.Tk()
    app = PDFVerifierGUI(root)
    
    # 設定關閉事件
    def on_closing():
        if app.processing:
            if messagebox.askokcancel("確認", "處理正在進行中，確定要關閉程式嗎？"):
                app.processing = False
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # 啟動GUI
    root.mainloop()


if __name__ == "__main__":
    main()