---
name: "🐛 Bug 报告"
description: "报告项目中的错误或问题"
title: "[BUG] "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        感谢您报告问题！请提供以下信息帮助我们快速定位和修复问题。

  - type: textarea
    id: description
    attributes:
      label: "问题描述"
      description: "请清晰描述遇到的问题"
      placeholder: "当我执行...时，发生了...错误"
    validations:
      required: true

  - type: textarea
    id: steps
    attributes:
      label: "复现步骤"
      description: "请提供详细的复现步骤"
      placeholder: |
        1. 执行命令 '...'
        2. 设置环境变量 '...'
        3. 看到错误 '...'
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: "期望行为"
      description: "您期望的正确行为是什么？"
      placeholder: "应该正常生成报告而不报错"
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: "实际行为"
      description: "实际发生了什么？"
      placeholder: "程序崩溃并显示错误信息"
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: "日志输出"
      description: "请提供相关的日志或错误信息"
      render: shell

  - type: dropdown
    id: environment
    attributes:
      label: "运行环境"
      multiple: true
      options:
        - "Docker"
        - "本地 Python"
        - "其他"

  - type: input
    id: version
    attributes:
      label: "项目版本"
      placeholder: "0.1.0"

  - type: textarea
    id: context
    attributes:
      label: "补充信息"
      description: "任何其他有助于解决问题的信息"
      placeholder: "操作系统、Python版本、相关配置等"