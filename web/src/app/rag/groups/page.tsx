"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, Edit2, Check, X } from "lucide-react";
import { LanguageSelect, getLanguageLabel } from "@/components/LanguageSelect";

interface Group {
  id: number;
  chat_name: string;
  source: string;
  device_id: string | null;
  default_language: string;
  rag_enabled: boolean;
  created_at: string;
}

export default function GroupsPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formData, setFormData] = useState({
    chat_name: "",
    source: "wechat",
    device_id: "",
    default_language: "pt",
    rag_enabled: true,
  });

  useEffect(() => {
    loadGroups();
  }, []);

  const loadGroups = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/rag/groups");
      const data = await res.json();
      setGroups(data.groups || []);
    } catch (error) {
      console.error("加载群组失败:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    try {
      const res = await fetch("/api/rag/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "添加失败");
      }

      setFormData({
        chat_name: "",
        source: "wechat",
        device_id: "",
        default_language: "pt",
        rag_enabled: true,
      });
      setShowForm(false);
      loadGroups();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleUpdate = async (id: number) => {
    const group = groups.find((g) => g.id === id);
    if (!group) return;

    try {
      await fetch(`/api/rag/groups/${encodeURIComponent(group.chat_name)}?source=${group.source}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          default_language: group.default_language,
          rag_enabled: group.rag_enabled,
        }),
      });
      setEditingId(null);
      loadGroups();
    } catch (error) {
      console.error("更新失败:", error);
    }
  };

  const handleDelete = async (chat_name: string, source: string) => {
    if (!confirm("确定要删除这个群组配置吗？")) return;

    try {
      await fetch(
        `/api/rag/groups/${encodeURIComponent(chat_name)}?source=${source}`,
        { method: "DELETE" }
      );
      loadGroups();
    } catch (error) {
      console.error("删除失败:", error);
    }
  };

  const updateGroupField = (id: number, field: string, value: any) => {
    setGroups(
      groups.map((g) => (g.id === id ? { ...g, [field]: value } : g))
    );
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">群组配置</h1>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          <Plus size={16} />
          添加群组
        </button>
      </div>

      {/* 添加表单 */}
      {showForm && (
        <div className="border border-gray-200 rounded-lg p-6 mb-6 space-y-4">
          <h2 className="text-lg font-semibold">添加新群组</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                群名/聊天名称
              </label>
              <input
                type="text"
                value={formData.chat_name}
                onChange={(e) =>
                  setFormData({ ...formData, chat_name: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded"
                placeholder="输入群名或联系人名"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                来源
              </label>
              <select
                value={formData.source}
                onChange={(e) =>
                  setFormData({ ...formData, source: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded"
              >
                <option value="wechat">微信</option>
                <option value="whatsapp">WhatsApp</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                设备 ID（可选）
              </label>
              <input
                type="text"
                value={formData.device_id}
                onChange={(e) =>
                  setFormData({ ...formData, device_id: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded"
                placeholder="设备序列号"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                默认语言
              </label>
              <LanguageSelect
                value={formData.default_language}
                onChange={(v) => setFormData({ ...formData, default_language: v })}
                className="w-full px-3 py-2 border border-gray-300 rounded bg-white text-sm"
              />
            </div>
            <div className="flex items-center">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.rag_enabled}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      rag_enabled: e.target.checked,
                    })
                  }
                  className="h-4 w-4"
                />
                <span className="text-sm text-gray-700">启用 RAG 问答</span>
              </label>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleAdd}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              保存
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* 群组列表 */}
      {loading ? (
        <div className="text-center py-12">加载中...</div>
      ) : groups.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          暂无群组配置，点击"添加群组"开始配置
        </div>
      ) : (
        <div className="grid gap-4">
          {groups.map((group) => (
            <div
              key={group.id}
              className="border border-gray-200 rounded-lg p-4"
            >
              {editingId === group.id ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        默认语言
                      </label>
                      <LanguageSelect
                        value={group.default_language}
                        onChange={(v) => updateGroupField(group.id, "default_language", v)}
                        className="w-full px-3 py-2 border border-gray-300 rounded bg-white text-sm"
                      />
                    </div>
                    <div className="flex items-end">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={group.rag_enabled}
                          onChange={(e) =>
                            updateGroupField(
                              group.id,
                              "rag_enabled",
                              e.target.checked
                            )
                          }
                          className="h-4 w-4"
                        />
                        <span className="text-sm text-gray-700">
                          启用 RAG 问答
                        </span>
                      </label>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => handleUpdate(group.id)}
                      className="flex items-center gap-1 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                    >
                      <Check size={14} />
                      保存
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="flex items-center gap-1 px-3 py-1 bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                    >
                      <X size={14} />
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold text-lg">
                      {group.chat_name}
                      <span className="ml-2 text-sm font-normal text-gray-500">
                        ({group.source})
                      </span>
                    </h3>
                    <div className="flex gap-4 mt-2 text-sm text-gray-600">
                      <span>默认语言：{getLanguageLabel(group.default_language)}</span>
                      <span>RAG：{group.rag_enabled ? "已启用" : "已禁用"}</span>
                      {group.device_id && <span>设备：{group.device_id}</span>}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setEditingId(group.id)}
                      className="text-blue-600 hover:text-blue-800 p-2"
                    >
                      <Edit2 size={18} />
                    </button>
                    <button
                      onClick={() =>
                        handleDelete(group.chat_name, group.source)
                      }
                      className="text-red-600 hover:text-red-800 p-2"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
