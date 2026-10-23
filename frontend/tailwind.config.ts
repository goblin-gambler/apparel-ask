/**
 * Tailwind CSS 主题配置
 * 定义前端项目的字体、颜色和阴影扩展
 * 视觉基调：宣纸、墨色、青瓷、朱砂
 */
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "sans-serif",
        ],
        serif: [
          '"Noto Serif SC"',
          '"Songti SC"',
          '"STSong"',
          '"SimSun"',
          "serif",
        ],
        mono: ['"JetBrains Mono"', '"SFMono-Regular"', "Consolas", "monospace"],
      },
      colors: {
        paper: "#f5f0e7",
        parchment: "#f5f0e7",
        ink: "#1b1a17",
        soot: "#141310",
        moss: "#3f5c4e",
        celadon: "#3f5c4e",
        brass: "#a98545",
        gold: "#a98545",
        tomato: "#a64232",
        cinnabar: "#a64232",
        mist: "#ddd6c8",
      },
      boxShadow: {
        line: "0 1px 0 rgba(27, 26, 23, 0.07)",
        panel: "0 18px 50px rgba(27, 26, 23, 0.12)",
      },
      letterSpacing: {
        seal: "0.32em",
      },
    },
  },
  plugins: [],
} satisfies Config;
