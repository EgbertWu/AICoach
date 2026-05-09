import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Tailwind CSS v4 的 Vite 插件，替代了旧版的 PostCSS 配置方式
    tailwindcss(),
  ],

  // ===== 开发服务器配置 =====
  server: {
    port: 3000, // 前端开发服务器端口（与后端 8000 区分）

    // API 代理配置（解决前后端分离的跨域问题）
    //
    // 为什么需要代理？
    // 在开发环境中，前端运行在 localhost:3000，后端运行在 localhost:8000。
    // 浏览器的同源策略（Same-Origin Policy）会阻止前端直接请求不同端口的后端 API，
    // 导致 CORS（跨域资源共享）错误。
    //
    // 通过 Vite 的 proxy 配置，所有以 /api 开头的请求会被自动转发到后端服务器，
    // 对浏览器来说，请求和响应都来自同一个源（localhost:3000），从而绕过 CORS 限制。
    //
    // 生产环境中，通常通过 Nginx 反向代理实现类似效果。
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true, // 修改请求头中的 Origin 为目标 URL
      },
    },
  },
})
