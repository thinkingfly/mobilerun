"use client";

import React from "react";

export const LANGUAGE_GROUPS = [
  {
    label: "常用语言",
    options: [
      { value: "zh", label: "中文" },
      { value: "en", label: "英语 English" },
      { value: "pt", label: "葡萄牙语 Português" },
      { value: "es", label: "西班牙语 Español" },
      { value: "fr", label: "法语 Français" },
      { value: "de", label: "德语 Deutsch" },
      { value: "it", label: "意大利语 Italiano" },
      { value: "ru", label: "俄语 Русский" },
      { value: "ja", label: "日语 日本語" },
      { value: "ko", label: "韩语 한국어" },
    ],
  },
  {
    label: "东南亚",
    options: [
      { value: "vi", label: "越南语 Tiếng Việt" },
      { value: "th", label: "泰语 ภาษาไทย" },
      { value: "id", label: "印尼语 Bahasa Indonesia" },
      { value: "ms", label: "马来语 Bahasa Melayu" },
      { value: "tl", label: "菲律宾语 Filipino" },
    ],
  },
  {
    label: "欧洲其他",
    options: [
      { value: "nl", label: "荷兰语 Nederlands" },
      { value: "pl", label: "波兰语 Polski" },
      { value: "sv", label: "瑞典语 Svenska" },
      { value: "da", label: "丹麦语 Dansk" },
      { value: "no", label: "挪威语 Norsk" },
      { value: "fi", label: "芬兰语 Suomi" },
      { value: "tr", label: "土耳其语 Türkçe" },
      { value: "uk", label: "乌克兰语 Українська" },
      { value: "ro", label: "罗马尼亚语 Română" },
      { value: "hu", label: "匈牙利语 Magyar" },
      { value: "cs", label: "捷克语 Čeština" },
      { value: "el", label: "希腊语 Ελληνικά" },
      { value: "bg", label: "保加利亚语 Български" },
    ],
  },
  {
    label: "中东/南亚",
    options: [
      { value: "ar", label: "阿拉伯语 العربية" },
      { value: "he", label: "希伯来语 עברית" },
      { value: "fa", label: "波斯语 فارسی" },
      { value: "hi", label: "印地语 हिन्दी" },
      { value: "bn", label: "孟加拉语 বাংলা" },
      { value: "ur", label: "乌尔都语 اردو" },
      { value: "ta", label: "泰米尔语 தமிழ்" },
    ],
  },
  {
    label: "非洲",
    options: [
      { value: "sw", label: "斯瓦希里语 Kiswahili" },
      { value: "am", label: "阿姆哈拉语 አማርኛ" },
    ],
  },
];

// 代码 → 中文名（用于列表展示）
export const LANG_LABELS: Record<string, string> = Object.fromEntries(
  LANGUAGE_GROUPS.flatMap((g) => g.options.map((o) => [o.value, o.label.split(" ")[0]]))
);

export function getLanguageLabel(code: string): string {
  return LANG_LABELS[code] || code.toUpperCase();
}

interface LanguageSelectProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  showAuto?: boolean;
}

export function LanguageSelect({ value, onChange, className, showAuto }: LanguageSelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={className || "w-full px-3 py-2 border border-gray-300 rounded-md bg-white text-sm"}
    >
      {showAuto && (
        <option value="auto">自动检测（推荐）</option>
      )}
      {LANGUAGE_GROUPS.map((group) => (
        <optgroup key={group.label} label={group.label}>
          {group.options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
