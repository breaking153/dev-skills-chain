# 概念

TypeScript（TS）在 JavaScript 语法上增加静态类型等开发能力。类型检查帮助开发者提前发现问题；类型标注会在转换为 JavaScript 时移除，生成的 JavaScript 由浏览器或 Node.js 等环境执行。

下面的例子说明类型标注与运行代码的关系。

`src/index.ts`：

```ts
function add(a: number, b: number): number {
  return a + b;
}

console.log(add(1, 2));
```

转换后的关键代码：

```js
function add(a, b) {
  return a + b;
}

console.log(add(1, 2));
```

两者表达相同的加法逻辑；类型信息只参与开发时检查。运行 JavaScript 后，预期输出为 `3`。

## 类型声明

`.d.ts` 文件描述 JavaScript API 的类型。声明可以来自包自身、`@types` 包或项目自行维护的文件。类型声明让编译器知道 API 的形状，不会替代 API 的实际实现。

### `typeRoots`

`typeRoots` 用于指定类型包的搜索目录。没有自定义目录需求时，通常保留默认行为；显式指定后，要注意原本自动可见的类型包是否仍在搜索范围内。参见 [TypeScript typeRoots](https://www.typescriptlang.org/tsconfig/typeRoots.html)。

```json
{
  "compilerOptions": {
    "typeRoots": ["./node_modules/@types", "./types"]
  }
}
```

这里的目录用于类型包发现，不等同于运行时模块搜索路径。

# 安装

项目已安装 Node.js 和 npm，且存在 `package.json` 时，可以把 TypeScript 安装为开发依赖，让版本随项目依赖管理。

```bash
npm install --save-dev typescript
npx tsc --version
```

第二条命令用于检查项目可调用的编译器版本；具体版本以命令实际输出为准。

# 项目结构

## 初始化项目

在项目目录创建编译配置：

```bash
npx tsc --init
```

该命令生成 `tsconfig.json`。不同 TypeScript 版本生成的默认内容可能不同，后续应结合项目的运行环境调整。

## 项目构成

```text
project/
├── package.json
├── package-lock.json
├── tsconfig.json
└── src/
    └── index.ts
```

| 文件或目录 | 职责 |
| --- | --- |
| `package.json` | 声明项目依赖和脚本 |
| `package-lock.json` | 锁定 npm 解析得到的依赖信息 |
| `tsconfig.json` | 描述检查范围与编译行为 |
| `src/` | 保存项目源代码 |

## `tsconfig.json`

`tsconfig.json` 把项目输入与编译选项放在同一份配置中。以下配置用于编译前面的单文件例子：

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "CommonJS",
    "strict": true,
    "rootDir": "src",
    "outDir": "dist"
  },
  "include": ["src"]
}
```

该示例假设项目按 CommonJS 运行；如果 `package.json` 声明了其他模块模式，应先让编译配置与运行环境匹配。

### `paths`

`paths` 为 TypeScript 的模块解析提供路径映射。它不会自动改写生成的 JavaScript 导入路径，因此运行环境或构建工具也需要理解相同映射。参见 [TypeScript paths](https://www.typescriptlang.org/tsconfig/paths.html)。

```json
{
  "compilerOptions": {
    "paths": {
      "@core/*": ["./src/core/*"]
    }
  }
}
```

此处的重点是区分“编译器能找到模块”与“运行时能加载模块”。这段配置用于说明该字段，不要求加入上面的加法示例。

### `references`

`references` 是顶层字段，用于声明当前 TypeScript 项目依赖哪些其他 TypeScript 项目。它与 `compilerOptions` 同级，主要服务于多项目检查与构建。参见 [TypeScript Project References](https://www.typescriptlang.org/docs/handbook/project-references.html)。

```json
{
  "compilerOptions": {
    "strict": true
  },
  "references": [
    { "path": "../core" }
  ]
}
```

#### 与 `import` 的关系

`references` 描述项目之间的编译依赖；源码中的 `import` 表达当前文件使用哪些导出。两者职责不同，配置项目引用后，源码仍需要按模块规则导入所用对象。

```text
app 的 tsconfig.json
  └── references → core 项目

app 的源文件
  └── import → core 导出的对象
```

这张图只区分两种关系，不表示增加 `references` 就能自动完成包名解析。完整 Project References 工程还需要被引用项目的配置与声明输出。

# 命令行

## 编译

回到前面的单文件加法项目，在项目根目录执行：

```bash
npx tsc
node dist/index.js
```

按示例配置，编译产物位于 `dist/`；运行后的预期输出为 `3`。这是用于说明结构的示例，本文不把预期结果视为实际执行记录。

### Reference 构建模式

对于已正确配置 Project References 的工程，可以通过构建模式处理项目依赖。`references` 的字段职责见前面的配置章节，这里只说明命令入口：

```bash
npx tsc -b
```

构建模式根据项目依赖关系判断构建顺序；它不是前面单文件示例必须使用的命令。

## Watch 模式

```bash
npx tsc --watch
```

该命令持续监听相关文件变化，并重新执行必要的检查或编译。输出行为仍由 `tsconfig.json` 控制。
