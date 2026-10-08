<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "./api";

const data = ref<string>("加载中...");
onMounted(async () => {
  try {
    data.value = await api.hello();
  } catch (e) {
    data.value = "接口调用失败：" + String(e);
  }
});
</script>

<template>
  <div style="max-width: 800px; margin: 40px auto; font-family: sans-serif;">
    <h1>Vue + 后端 脚手架</h1>
    <p>后端返回：{{ data }}</p>
    <p>从这里开始改你的应用。</p>
  </div>
</template>
