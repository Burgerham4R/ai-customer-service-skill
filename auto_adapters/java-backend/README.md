# java-backend 适配器

将 conversation-core 骨架以 Filter 形式接入 Spring Boot / Quarkus 项目。

| 框架 | 模板 | 默认目标 |
|:---|:---|:---|
| Spring Boot | `springboot/VoiceAgentFilter.java.tpl` | `src/main/java/com/example/voiceagent/VoiceAgentFilter.java` |
| Quarkus     | `quarkus/VoiceAgentFilter.java.tpl`    | 同上 |

## 配置

`application.yml` / `application.properties`：

```yaml
skeleton:
  base-url: ${SKELETON_BASE_URL}
  api-prefix: ${API_PREFIX}
  route-prefix: ${ROUTE_PREFIX}
```

## 注意

- 模板中 `package com.example.voiceagent` 由 Agent 在 L1 渲染时根据用户项目实际包名替换。
- 默认 `connectTimeout=3s`、`request timeout=10s`，可按需调整。
- Spring Boot 注册 `voiceAgentFilter` 顺序为 10，应早于业务 Filter。
