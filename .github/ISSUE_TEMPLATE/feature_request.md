---
name: "✨ 功能请求"
description: "为项目提出新功能或改进建议"
title: "[FEATURE] "
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        感谢您为项目提出改进建议！请详细描述您的需求。

  - type: textarea
    id: description
    attributes:
      label: "功能描述"
      description: "请清晰描述您希望添加的功能"
      placeholder: "我希望能够..."
    validations:
      required: true

  - type: textarea
    id: problem
    attributes:
      label: "解决的问题"
      description: "这个功能解决了什么具体问题？"
      placeholder: "目前需要手动...，希望自动化处理"
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: "建议的解决方案"
      description: "您认为应该如何实现这个功能？"
      placeholder: "可以添加一个新的...模块来处理..."

  - type: textarea
    id: alternatives
    attributes:
      label: "替代方案"
      description: "您考虑过哪些替代方案？为什么选择这个方案？"

  - type: checkboxes
    id: context
    attributes:
      label: "使用场景"
      description: "这个功能在什么场景下使用？（可多选）"
      options:
        - label: "个人使用"
        - label: "团队协作"
        - label: "生产环境"
        - label: "开发测试"
        - label: "其他（请在下方说明）"

  - type: textarea
    id: examples
    attributes:
      label: "使用示例"
      description: "请提供具体的使用场景或代码示例"
      placeholder: "例如：当用户执行...时，应该..."

  - type: textarea
    id: additional
    attributes:
      label: "补充信息"
      description: "任何其他相关信息（截图、参考链接等）"

  - type: checkboxes
    id: contribution
    attributes:
      label: "贡献意愿"
      description: "您是否愿意参与实现这个功能？"
      options:
        - label: "我愿意提交 Pull Request 实现这个功能"
        - label: "我可以提供技术指导或测试帮助"
        - label: "目前只能提供想法，希望社区实现"