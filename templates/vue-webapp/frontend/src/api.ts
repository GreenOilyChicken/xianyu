// 统一封装后端接口调用。改 BASE 即可切换后端地址。
import axios from "axios";

const http = axios.create({ baseURL: "/api", timeout: 10000 });

export const api = {
  async hello(): Promise<string> {
    const { data } = await http.get("/hello");
    return data.message ?? String(data);
  },
};
