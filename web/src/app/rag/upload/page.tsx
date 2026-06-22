"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, ArrowLeft } from "lucide-react";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("auto");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

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
        router.push("/rag");
      }, 2000);
    } catch (err: any) {
      setError(err.message || "上传失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="container mx-auto p-6 max-w-2xl">
      <div className="mb-6">
        <Link
          href="/rag"
          className="flex items-center gap-2 text-gray-600 hover:text-gray-800"
        >
          <ArrowLeft size={16} />
          返回文档管理
        </Link>
      </div>

      <h1 className="text-2xl font-bold mb-6">上传文档</h1>

      <div className="border border-gray-200 rounded-lg p-6 space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            选择文件
          </label>
          <input
            type="file"
            accept=".docx,.doc,.pdf"
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
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="block w-full px-3 py-2 border border-gray-300 rounded-md"
          >
            <option value="auto">自动检测</option>
            <option value="pt">葡萄牙语</option>
            <option value="zh">中文</option>
            <option value="en">英语</option>
            <option value="es">西班牙语</option>
          </select>
          <p className="mt-1 text-sm text-gray-500">
            如果不确定语言，选择"自动检测"
          </p>
        </div>

        {error && (
          <div className="p-3 bg-red-50 text-red-700 rounded">{error}</div>
        )}

        {success && (
          <div className="p-3 bg-green-50 text-green-700 rounded">{success}</div>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          <Upload size={16} />
          {uploading ? "上传中..." : "上传文档"}
        </button>
      </div>
    </div>
  );
}

function Link({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <a href={href} className={className}>
      {children}
    </a>
  );
}
