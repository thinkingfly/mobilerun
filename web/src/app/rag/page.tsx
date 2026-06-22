"use client";

import { useEffect, useState, useRef } from "react";
import { FileText, Upload, Trash2, RefreshCw, X } from "lucide-react";
import { LanguageSelect, getLanguageLabel } from "@/components/LanguageSelect";

interface Document {
  id: number;
  filename: string;
  language: string;
  chunk_count: number;
  uploaded_at: string;
  status: string;
}

export default function RagDocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/rag/documents");
      const data = await res.json();
      setDocuments(data.documents || []);
    } catch (error) {
      console.error("加载文档失败:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定要删除这个文档吗？")) return;

    try {
      await fetch(`/api/rag/documents/${id}`, { method: "DELETE" });
      setDocuments(documents.filter((doc) => doc.id !== id));
    } catch (error) {
      console.error("删除文档失败:", error);
      alert("删除失败");
    }
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">文档管理</h1>
        <div className="flex gap-3">
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            <Upload size={16} />
            上传文档
          </button>
          <button
            onClick={loadDocuments}
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
          >
            <RefreshCw size={16} />
            刷新
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12">加载中...</div>
      ) : documents.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          暂无文档，点击"上传文档"开始添加
        </div>
      ) : (
        <div className="grid gap-4">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <FileText className="text-blue-600 mt-1" size={24} />
                  <div>
                    <h3 className="font-semibold text-lg">{doc.filename}</h3>
                    <div className="flex gap-4 mt-2 text-sm text-gray-600">
                      <span>语言：{getLanguageLabel(doc.language)}</span>
                      <span>切片数：{doc.chunk_count}</span>
                      <span>上传时间：{new Date(doc.uploaded_at).toLocaleString("zh-CN")}</span>
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(doc.id)}
                  className="text-red-600 hover:text-red-800 p-2"
                  title="删除文档"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 上传文档弹窗 */}
      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUploaded={() => {
            setShowUpload(false);
            loadDocuments();
          }}
        />
      )}
    </div>
  );
}

function UploadModal({
  onClose,
  onUploaded,
}: {
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("auto");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const backdropRef = useRef<HTMLDivElement>(null);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current) {
      onClose();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      const ext = selectedFile.name.split(".").pop()?.toLowerCase();
      if (!["docx", "doc", "pdf", "txt"].includes(ext || "")) {
        setError("只支持 .docx、.pdf 和 .txt 文件");
        return;
      }
      setFile(selectedFile);
      setError("");
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError("请选择文件");
      return;
    }

    setUploading(true);
    setError("");
    setSuccess("");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("language", language);

    try {
      const res = await fetch("/api/rag/documents/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "上传失败");
      }

      setSuccess(`上传成功！文档 ID: ${data.id}, 切片数：${data.chunk_count}`);
      setTimeout(() => {
        onUploaded();
      }, 1500);
    } catch (err: any) {
      setError(err.message || "上传失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold">上传文档</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded hover:bg-gray-100"
            title="关闭"
          >
            <X size={20} />
          </button>
        </div>

        {/* 内容 */}
        <div className="px-6 py-5 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              选择文件
            </label>
            <input
              type="file"
              accept=".docx,.doc,.pdf,.txt"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            {file && (
              <p className="mt-2 text-sm text-gray-600">
                已选择：{file.name} ({(file.size / 1024).toFixed(1)} KB)
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              语言标记
            </label>
            <LanguageSelect
              value={language}
              onChange={setLanguage}
              showAuto
            />
            <p className="mt-1 text-sm text-gray-500">
              如果不确定语言，选择"自动检测"
            </p>
          </div>

          {error && (
            <div className="p-3 bg-red-50 text-red-700 rounded text-sm">{error}</div>
          )}

          {success && (
            <div className="p-3 bg-green-50 text-green-700 rounded text-sm">{success}</div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded hover:bg-gray-200"
          >
            取消
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            <Upload size={16} />
            {uploading ? "上传中..." : "上传"}
          </button>
        </div>
      </div>
    </div>
  );
}
