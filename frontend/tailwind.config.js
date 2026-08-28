/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Monospace display + body for the "instrument" aesthetic.
        // CJK fallbacks come before the generic families: without them a
        // zh-CN Windows box renders Chinese text (user/project names) in
        // SimSun, which is proportional and jarring next to JetBrains Mono.
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", '"Noto Sans Mono CJK SC"', '"Microsoft YaHei"', '"PingFang SC"', "monospace"],
        sans: ['"Inter"', "system-ui", '"PingFang SC"', '"Microsoft YaHei"', "sans-serif"],
      },
      colors: {
        // Mission-control palette: deep ink, hairline rules, signal amber.
        ink: {
          950: "#0B0D10",
          900: "#13161B",
          800: "#1B1F26",
          700: "#232831",
          600: "#2C333E",
        },
        signal: {
          DEFAULT: "#FF7A3D", // signal amber
          dim: "#B85426",
        },
        mint: {
          DEFAULT: "#6FE3C2",
        },
        sun: {
          DEFAULT: "#FFB454",
        },
        muted: "#8A93A1",
        fg: "#E6E9EF",
      },
      letterSpacing: {
        widest2: "0.18em",
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.02), inset 0 0 0 1px rgba(255,255,255,0.04)",
      },
    },
  },
  plugins: [],
};