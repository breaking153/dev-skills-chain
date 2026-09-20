# 概念

EDR 的驱动层组件主要利用 Windows 在进程生命周期、对象句柄操作、注册表访问、文件系统 I/O 和网络处理过程中提供的扩展点，采集行为信息，并在接口允许的阶段执行访问控制。

通常所说的“驱动层 Hook”包含几种不同机制。学习时应首先区分：**修改内核执行路径的 Hook、系统提供的通知回调，以及专门的过滤框架，不是同一种实现方式。** Windows 为进程与线程管理、对象操作、注册表和文件系统分别提供了不同的接口。:chatgpt-content-reference{index="0"}

本文以 Windows x64 为范围，重点整理公开、受支持的驱动接口，不涉及修改未公开回调数组、内核代码补丁或第三方驱动内部结构。

## Hook、Callback 与过滤框架

### 修改执行路径的 Hook

狭义的 Hook 通常指改变原有调用路径，使执行流程进入自己的代码，例如修改函数入口或函数分发表。

这与“向操作系统登记一个回调函数”不同。Windows x64 对内核代码及部分关键数据结构有保护限制，直接修改这些受保护区域可能导致系统错误。不能把修改内核代码当作与官方回调注册等价的驱动开发方式。:chatgpt-content-reference{index="1"}

### 系统通知回调

通知回调的基本流程是：

```text
驱动注册回调函数
    ↓
操作系统保存注册信息
    ↓
某个受支持的系统事件发生
    ↓
对应内核子系统调用驱动的回调函数
    ↓
驱动处理事件并返回
```

例如，调用 `PsSetCreateProcessNotifyRoutineEx`，是在注册进程创建和退出通知，并不是替换 `CreateProcess`、`NtCreateUserProcess` 或其他函数的入口。:chatgpt-content-reference{index="2"}

需要特别区分：

- 有的回调只提供通知，例如线程创建通知、镜像加载通知。
- 有的回调允许修改操作结果，例如进程创建通知中的 `CreationStatus`。
- 有的回调只允许限制特定参数，例如对象回调中的句柄访问权限。

**存在回调，不代表可以通过任意返回值阻断操作。控制能力由具体接口的契约决定。**:chatgpt-content-reference{index="3"}

### 专门的过滤框架

文件系统和网络具有更复杂的处理阶段，因此 Windows 提供了专门的过滤框架：

| 框架 | 所属处理领域 | 驱动接入方式 |
|---|---|---|
| Minifilter / FltMgr | 文件系统 I/O | 注册操作回调，由 Filter Manager 管理过滤实例和 I/O 流转。 |
| WFP | 网络连接、数据流和数据包处理 | 配置过滤层与过滤器，必要时注册内核 Callout 执行自定义处理。 |

Minifilter 并不是“文件版 `ObRegisterCallbacks`”，WFP 也不是“网络版进程通知”。它们分别具有自己的对象、执行阶段、排序方式和资源生命周期。:chatgpt-content-reference{index="4"}

## 内核对象、句柄与访问权限

理解 `Ob*` 之前，需要先区分进程对象和进程句柄。

**进程对象**表示内核维护的进程实体。**进程句柄**则是调用方用于访问该对象的引用入口，并且携带一组访问权限。

例如，一个程序获得另一个进程的句柄，不代表它自动拥有该进程的全部控制能力。终止进程、写入进程内存、创建线程等操作分别需要对应的访问权限。:chatgpt-content-reference{index="5"}

```text
调用方进程 A
    │
    ├─ 句柄 H1：指向进程 B，具有查询权限
    │
    └─ 句柄 H2：指向进程 B，具有查询和终止权限

内核中的进程 B 对象仍然只有一个。
```

由此可以区分两个完全不同的问题：

> 进程 B 是否正在创建或退出，是生命周期问题。
> 进程 A 正在申请怎样的权限来访问 B，是句柄授权问题。

`Ps*` 和 `Ob*` 正是分别处理这两类问题，后文会进一步说明它们在同一操作链中的关系。

## 主要接口的职责边界

`Ps`、`Ob`、`Cm` 等是内核子系统的函数命名前缀，并不表示该前缀下的所有函数都是回调注册函数。

| 接口族或框架 | 主要关注对象 | 典型控制能力 |
|---|---|---|
| `Ps*` | 进程创建与退出、线程创建与退出、镜像加载。 | 进程创建 Ex 回调可否决创建；线程和镜像通知没有同等的阻断返回接口。 |
| `Ob*` | 支持的对象类型的句柄创建、句柄复制。 | 在 Pre 回调中削减文档允许修改的访问权限。 |
| `Cm*` | 注册表操作。 | 在 Pre 阶段阻断；按接口规则处理输出和返回状态。 |
| `Flt*` / Minifilter | 文件系统 I/O。 | 放行、完成操作、特定路径下挂起，以及处理完成结果。 |
| `Fwps*`、`Fwpm*` / WFP | 网络授权和网络数据处理。 | 按过滤层和动作类型进行允许、阻断或自定义处理。 |

这些机制组合起来形成内核侧的观测和控制面，但单个接口并不能覆盖全部终端行为。:chatgpt-content-reference{index="6"}

# 开发环境

以下示例选择 **Windows 11 x64 测试虚拟机**作为说明环境，不代表用户现有环境。

驱动开发需要 Visual Studio、Windows SDK 和 WDK 配套使用。应按照 WDK 下载页面选择受支持的工具组合；SDK 与 WDK 的构建版本需要匹配，不宜简单地把各组件分别升级到任意“最新版本”后混用。:chatgpt-content-reference{index="7"}

驱动加载还受到代码签名策略约束。测试签名、正式签名以及系统当前启用的代码完整性配置，需要分别核对；“编译出了 `.sys` 文件”不等于“系统一定允许加载”。:chatgpt-content-reference{index="8"}

驱动实验应在可以恢复快照的独立虚拟机中进行。Driver Verifier 会主动检查违规行为，并可能通过蓝屏暴露错误，因此不应直接在生产终端上对实验驱动进行压力验证。:chatgpt-content-reference{index="9"}

本文代码只展示核心注册和处理逻辑：

- `...` 表示省略的初始化、异常处理或工程代码。
- `Policy*`、`CopyAndQueue*`、`IsLab*` 等名称是示例辅助函数，不是 WDK API。
- 这些片段没有在本文中实际编译或运行，不能直接拼接后当作完整驱动部署。

# 项目结构

下面是一种用于学习的示意结构。它按内核功能域拆分代码，不要求每个模块都编译成独立的 `.sys`。

```text
EdrLab/
├─ driver/
│  ├─ entry.c             # 初始化、失败回滚、统一退出
│  ├─ process.c           # Ps：进程、线程、镜像通知
│  ├─ object.c            # Ob：进程和线程句柄过滤
│  ├─ registry.c          # Cm：注册表过滤
│  ├─ file.c              # Minifilter：文件系统过滤
│  ├─ network.c           # WFP：内核 Callout
│  ├─ policy.c            # 内核本地策略快照
│  ├─ events.c            # 有界事件队列和工作项
│  └─ EdrLab.inf          # 驱动安装与过滤实例相关配置
├─ shared/
│  └─ protocol.h          # 驱动和服务之间的数据协议
├─ service/
│  ├─ main.cpp            # 策略管理、事件消费和持久化
│  └─ wfp_policy.cpp      # WFP 管理对象和过滤器配置
└─ tests/
   ├─ process_test.cpp
   ├─ handle_test.cpp
   ├─ registry_test.cpp
   ├─ file_test.cpp
   └─ network_test.cpp
```

在这条示例路径中，驱动负责短时间内可以完成的事件采集和本地策略判断，用户态服务负责日志存储、信息补充和较复杂的分析。

不能把用户态服务设计成所有内核回调的同步裁决中心。微软对进程、线程、镜像和对象通知的最佳实践明确要求：避免在回调中调用用户态服务、进行阻塞式进程间通信，或等待其他工作线程完成任务。:chatgpt-content-reference{index="10"}

# 进程、线程与镜像通知

`Ps*` 相关通知主要提供三个维度的信息：

```text
进程生命周期：哪个进程正在创建或退出。
线程生命周期：哪个进程中的哪个线程正在创建或退出。
镜像加载：哪个地址空间中映射了什么镜像。
```

它们描述的事件对象不同，不应把所有记录都解释成“进程创建事件”。

## 进程通知

### 注册接口与版本

| 注册接口 | 主要特点 |
|---|---|
| `PsSetCreateProcessNotifyRoutine` | 传统进程创建、退出通知。回调没有 `CreationStatus` 字段。 |
| `PsSetCreateProcessNotifyRoutineEx` | 提供 `PS_CREATE_NOTIFY_INFO`，可以获取更多创建信息，并允许否决创建。最低支持 Windows Vista SP1 / Windows Server 2008。 |
| `PsSetCreateProcessNotifyRoutineEx2` | 进一步通过通知类型支持子系统进程等场景。最低支持 Windows 10 1703。 |

`Ex2` 的主要区别之一是通知覆盖类型，而不是“比 Ex 多出一个通用任意阻断能力”。:chatgpt-content-reference{index="11"}

### 创建信息与身份关系

Ex 回调的核心参数是：

```c
VOID OnProcessNotify(
    PEPROCESS Process,
    HANDLE ProcessId,
    PPS_CREATE_NOTIFY_INFO CreateInfo
);
```

`CreateInfo != NULL` 表示创建通知；`CreateInfo == NULL` 表示退出通知。`Process` 和 `ProcessId` 指向的是正在创建或退出的目标进程。:chatgpt-content-reference{index="12"}

`PS_CREATE_NOTIFY_INFO` 中需要重点理解的字段如下：

| 字段 | 含义 |
|---|---|
| `ParentProcessId` | 新进程的父进程 ID。 |
| `CreatingThreadId.UniqueProcess` | 实际发起创建操作的进程 ID。 |
| `CreatingThreadId.UniqueThread` | 实际发起创建操作的线程 ID。 |
| `FileObject` | 进程可执行文件对应的文件对象。 |
| `ImageFileName` | 可执行文件名称；不能无条件认为它是完整、规范化的路径。 |
| `FileOpenNameAvailable` | 表示名称是否是用于打开可执行文件的准确名称。 |
| `CommandLine` | 创建命令行，可能为空。 |
| `CreationStatus` | 创建操作的状态，驱动可以把它改为失败状态。 |

**父进程不一定是实际创建者。** 事件模型应分别记录父进程关系和创建者关系，不能只保存一个含糊的“来源 PID”。部分子系统进程还可能没有 `FileObject`、`ImageFileName` 或 `CommandLine`。:chatgpt-content-reference{index="13"}

### 创建阻断

`process.c` 中可以使用下面的核心逻辑：

```c
VOID OnProcessNotify(
    PEPROCESS Process,
    HANDLE ProcessId,
    PPS_CREATE_NOTIFY_INFO CreateInfo
)
{
    if (CreateInfo == NULL) {
        CopyAndQueueProcessExit(ProcessId);
        return;
    }

    // 只使用已经准备好的本地策略。
    // 不把其他组件已经设置的失败状态改回成功。
    if (NT_SUCCESS(CreateInfo->CreationStatus) &&
        PolicyRejectsLabProcess(CreateInfo)) {

        CreateInfo->CreationStatus = STATUS_ACCESS_DENIED;
    }

    // 在本次回调内复制所需字段，不能只保存 CreateInfo 指针。
    CopyAndQueueProcessCreate(ProcessId, CreateInfo);

    ...
}

NTSTATUS RegisterProcessMonitor(VOID)
{
    return PsSetCreateProcessNotifyRoutineEx(
        OnProcessNotify,
        FALSE
    );
}
```

这里阻断创建的方式是修改：

```c
CreateInfo->CreationStatus = STATUS_ACCESS_DENIED;
```

不是从回调中返回 `STATUS_ACCESS_DENIED`，因为回调返回类型是 `VOID`。

同时，驱动没有否决创建，只能说明“本驱动在这个节点没有拒绝”，不代表整个进程创建流程最终一定成功。创建状态仍可能受到其他检查和组件影响。:chatgpt-content-reference{index="14"}

注册 Ex 回调还有一个容易遗漏的条件：回调所在映像需要设置 `IMAGE_DLLCHARACTERISTICS_FORCE_INTEGRITY`。MSVC 链接器的 `/INTEGRITYCHECK` 与该标记有关，但这个标记不能替代完整的驱动签名要求。:chatgpt-content-reference{index="15"}

## 线程通知

主要注册入口是：

```c
PsSetCreateThreadNotifyRoutine(...);
PsSetCreateThreadNotifyRoutineEx(...);
```

基本回调提供目标进程 ID、线程 ID，以及创建或删除标志：

```c
VOID OnThreadNotify(
    HANDLE ProcessId,
    HANDLE ThreadId,
    BOOLEAN Create
)
{
    CopyAndQueueThreadEvent(
        ProcessId,
        ThreadId,
        Create
    );

    ...
}
```

`Create == TRUE` 表示线程创建，`FALSE` 表示线程删除。这个回调返回 `VOID`，没有类似进程创建 `CreationStatus` 的阻断字段。:chatgpt-content-reference{index="16"}

`PsSetCreateThreadNotifyRoutineEx` 从 Windows 10 开始提供。普通线程创建通知与 `PsCreateThreadNotifyNonSystem` 模式的执行上下文不同：后者的创建回调运行在新线程上下文中，不能直接把“当前执行回调的线程”统一解释为创建者线程。:chatgpt-content-reference{index="17"}

线程通知也不等于“线程注入告警”。基本参数没有直接给出完整的调用链、内存来源或恶意性判断。EDR 可以把线程事件与进程关系、句柄授权等信息关联，但这属于检测逻辑，而不是该回调自身的语义。

## 镜像加载通知

主要接口为：

```c
PsSetLoadImageNotifyRoutine(...);
PsSetLoadImageNotifyRoutineEx(...);
```

回调形式如下：

```c
VOID OnImageLoad(
    PUNICODE_STRING FullImageName,
    HANDLE ProcessId,
    PIMAGE_INFO ImageInfo
)
{
    CopyAndQueueImageLoad(
        ProcessId,
        FullImageName,          // 可能为空
        ImageInfo->ImageBase,
        ImageInfo->ImageSize,
        ImageInfo->SystemModeImage
    );

    ...
}
```

镜像加载通知发生在镜像映射之后、入口点调用之前。内核驱动镜像通知中的 `ProcessId` 为零，`FullImageName` 也可能为空，因此不能对所有记录使用同一套“用户进程加载 DLL”解释。:chatgpt-content-reference{index="18"}

`PsSetLoadImageNotifyRoutineEx` 从 Windows 10 1709 开始提供，可以通过标志扩展对不同体系结构镜像的通知覆盖，但它没有增加一个“返回失败即可拒绝镜像加载”的接口。:chatgpt-content-reference{index="19"}

需要保留三个边界：

**第一，加载通知不等于任意代码执行通知。** 它关注镜像映射，不是对所有可执行内存修改进行统一回调。

**第二，取消加载通知不是卸载目标镜像。** `PsRemoveLoadImageNotifyRoutine` 删除的是驱动自己的通知注册。

**第三，这套接口没有对应的通用镜像卸载通知。** 不能仅依赖这些记录维护一个永远准确的实时模块列表。:chatgpt-content-reference{index="20"}

# 对象句柄过滤

`ObRegisterCallbacks` 接入的是对象管理器的句柄操作阶段。其重点不是“目标进程做了什么”，而是“某个句柄正在被创建或复制，并准备获得哪些权限”。

该接口从 Windows Vista SP1 / Windows Server 2008 开始支持；回调所在内核映像还必须满足签名要求。:chatgpt-content-reference{index="21"}

## 支持的对象与操作

常用对象类型包括：

| 对象类型 | 表示的对象 |
|---|---|
| `PsProcessType` | 进程对象。 |
| `PsThreadType` | 线程对象。 |
| `ExDesktopObjectType` | 桌面对象，Windows 10 起支持。 |

不能因为内核中存在文件对象、令牌对象、注册表键对象，就认为它们都能通过 `ObRegisterCallbacks` 注册过滤。公开接口支持的对象类型是受限制的。:chatgpt-content-reference{index="22"}

需要注册的操作包括：

```c
OB_OPERATION_HANDLE_CREATE
OB_OPERATION_HANDLE_DUPLICATE
```

这里的 `HANDLE_CREATE` 指创建对象句柄，**不等于创建一个新进程对象**。这套操作类型也不是通用的句柄关闭通知或内存访问通知。:chatgpt-content-reference{index="23"}

## 访问权限裁剪

### 原始请求、当前请求与最终授权

Pre 回调中需要区分：

| 字段 | 含义 |
|---|---|
| `OriginalDesiredAccess` | 调用方最初申请的权限。 |
| `DesiredAccess` | 当前准备授予、且允许按规则进一步限制的权限。 |
| `Object` | 本次句柄指向的对象。 |
| `ObjectType` | 该对象的类型。 |
| `KernelHandle` | 该句柄是否为内核句柄。 |

过滤器可以削减文档允许修改的访问权限，不能增加权限，也不能重新恢复其他过滤器已经削减的权限。因此应在当前 `DesiredAccess` 上清除权限位，而不是从 `OriginalDesiredAccess` 重新构造授权结果。:chatgpt-content-reference{index="24"}

```c
// 正确表达进一步限制：
DesiredAccess &= ~RightsToRemove;

// 不应把 OriginalDesiredAccess 重新当成当前授权基准：
DesiredAccess = OriginalDesiredAccess;
```

文档列出的可修改进程权限包括 `PROCESS_TERMINATE`、`PROCESS_CREATE_THREAD`、`PROCESS_VM_OPERATION`、`PROCESS_VM_WRITE` 等。

不能因为某个权限位存在于 `ACCESS_MASK` 中，就推断 Ob 回调允许任意修改它。例如，官方该结构的可修改进程权限列表没有列出 `PROCESS_VM_READ`，不应把“可以随意清除所有进程访问权限”写成接口保证。:chatgpt-content-reference{index="25"}

### Pre 与 Post 的返回语义

Ob Pre 回调必须返回：

```c
OB_PREOP_SUCCESS
```

它没有“返回 `STATUS_ACCESS_DENIED`，直接让 `OpenProcess` 失败”的通用语义。限制通常通过修改 `DesiredAccess` 实现。:chatgpt-content-reference{index="26"}

这意味着：

```text
申请进程句柄
    ↓
Ob Pre 删除 PROCESS_TERMINATE
    ↓
系统仍可能成功返回一个权限受限的句柄
    ↓
随后使用该句柄终止进程时，因缺少权限而失败
```

因此，验证 Ob 防护不能只检查 `OpenProcess` 是否成功，还应检查实际授予权限，以及后续受保护操作是否成功。

Post 回调可以读取操作的 `ReturnStatus`；只有操作成功时，才能按文档读取 `Parameters` 中的实际授权结果，例如 `GrantedAccess`。Post 信息是只读的，不能在这里继续修改句柄权限。:chatgpt-content-reference{index="27"}

### 核心实现

下面只对指定实验进程的用户句柄进行权限限制：

```c
OB_PREOP_CALLBACK_STATUS OnObjectPre(
    PVOID RegistrationContext,
    POB_PRE_OPERATION_INFORMATION Info
)
{
    if (Info->ObjectType != *PsProcessType) {
        return OB_PREOP_SUCCESS;
    }

    // 本示例只验证用户句柄路径。
    // 跳过内核句柄是示例范围，不是“内核句柄天然可信”。
    if (Info->KernelHandle) {
        return OB_PREOP_SUCCESS;
    }

    if (!IsProtectedLabProcess((PEPROCESS)Info->Object)) {
        return OB_PREOP_SUCCESS;
    }

    ACCESS_MASK* desiredAccess = NULL;

    if (Info->Operation == OB_OPERATION_HANDLE_CREATE) {
        desiredAccess =
            &Info->Parameters->CreateHandleInformation.DesiredAccess;
    }
    else if (Info->Operation == OB_OPERATION_HANDLE_DUPLICATE) {
        desiredAccess =
            &Info->Parameters->DuplicateHandleInformation.DesiredAccess;
    }
    else {
        return OB_PREOP_SUCCESS;
    }

    *desiredAccess &= ~(
        PROCESS_TERMINATE |
        PROCESS_CREATE_THREAD |
        PROCESS_VM_OPERATION |
        PROCESS_VM_WRITE
    );

    return OB_PREOP_SUCCESS;
}

NTSTATUS RegisterObjectMonitor(PCUNICODE_STRING Altitude)
{
    OB_OPERATION_REGISTRATION operation = {0};

    operation.ObjectType = PsProcessType;
    operation.Operations =
        OB_OPERATION_HANDLE_CREATE |
        OB_OPERATION_HANDLE_DUPLICATE;
    operation.PreOperation = OnObjectPre;

    OB_CALLBACK_REGISTRATION registration = {0};

    registration.Version = OB_FLT_REGISTRATION_VERSION;
    registration.OperationRegistrationCount = 1;
    registration.Altitude = *Altitude;
    registration.OperationRegistration = &operation;

    return ObRegisterCallbacks(
        &registration,
        &gObjectRegistrationHandle
    );
}
```

注册结构中的 `ObjectType` 使用 `PsProcessType`；回调收到的 `Info->ObjectType` 与 `*PsProcessType` 比较。这是因为两处字段的指针层级不同。:chatgpt-content-reference{index="28"}

`Altitude` 用于对象回调的排序，重复高度可能导致注册失败。示例通过参数传入，不应直接复制其他产品的高度作为生产配置。:chatgpt-content-reference{index="29"}

## 句柄复制中的对象关系

句柄复制事件中容易混淆三个实体：

```text
源句柄所在进程 A
    │
    │ 复制一个指向 B 的句柄
    ↓
接收句柄的进程 C

句柄真正指向的对象仍然是进程 B。
```

对应字段为：

| 字段 | 对应实体 |
|---|---|
| `Info->Object` | 被句柄引用的对象 B。 |
| `DuplicateHandleInformation.SourceProcess` | 源句柄表所属进程 A。 |
| `DuplicateHandleInformation.TargetProcess` | 新句柄表所属进程 C。 |

这里的 `TargetProcess` 不是“被保护的目标对象”。把接收句柄的进程误认为被访问的进程，会直接导致策略判断和事件关联错误。:chatgpt-content-reference{index="30"}

## 与进程生命周期的关系

`Ps` 和 `Ob` 可能出现在同一条操作链中，但不是互相替代的重复监控。

| 操作场景 | Ps 生命周期通知 | Ob 句柄过滤 |
|---|---|---|
| 创建新进程 | 关注新进程的创建。 | 同一业务流程还可能涉及进程和线程句柄的建立。 |
| 打开已经存在的进程 | 不会因为打开句柄而重新产生该目标的进程创建通知。 | 关注新句柄申请及权限。 |
| 复制已有进程句柄 | 不会因为复制句柄而创建目标进程。 | 关注句柄复制及相关权限。 |
| 使用已有句柄写入目标进程 | 不是进程生命周期事件。 | 不能期待每次内存写入都重新触发一次句柄授权回调。 |

因此，“创建进程通常需要处理句柄”不意味着“进程通知与对象回调是同一个功能”。它们描述的是不同的系统语义节点。:chatgpt-content-reference{index="31"}

还应明确：注册 Ob 回调或更新策略，不等于追溯修改所有已经发出的句柄。设计和测试时，应把“策略生效后新申请的句柄”与“策略生效前已经持有的句柄”分别处理。

# 注册表过滤

`Cm` 对应 Configuration Manager，即 Windows 注册表相关的内核管理部分。

注册表过滤通过 `CmRegisterCallback` 或 `CmRegisterCallbackEx` 接入。现代示例通常使用支持高度和驱动对象参数的 `CmRegisterCallbackEx`，该接口从 Windows Vista 开始提供。它是注册表过滤注册，不需要先调用文件系统的 `FltRegisterFilter`。:chatgpt-content-reference{index="32"}

## 通知分类

注册表回调的形式是：

```c
NTSTATUS OnRegistryNotify(
    PVOID CallbackContext,
    PVOID Argument1,
    PVOID Argument2
);
```

这里：

- `Argument1` 承载 `REG_NOTIFY_CLASS` 枚举值。
- `Argument2` 指向与通知类别对应的信息结构。
- `CallbackContext` 是注册时传入的驱动自定义上下文。

`Argument1` 应转换成枚举值，而不是当作指向枚举的指针解引用。:chatgpt-content-reference{index="33"}

```c
REG_NOTIFY_CLASS notifyClass =
    (REG_NOTIFY_CLASS)(ULONG_PTR)Argument1;
```

常见操作包括：

| 操作 | 典型通知类别 |
|---|---|
| 创建注册表键 | `RegNtPreCreateKeyEx`、`RegNtPostCreateKeyEx` |
| 打开注册表键 | `RegNtPreOpenKeyEx`、`RegNtPostOpenKeyEx` |
| 设置注册表值 | `RegNtPreSetValueKey`、`RegNtPostSetValueKey` |
| 删除注册表值 | `RegNtPreDeleteValueKey`、`RegNtPostDeleteValueKey` |
| 删除注册表键 | `RegNtPreDeleteKey`、`RegNtPostDeleteKey` |
| 重命名注册表键 | `RegNtPreRenameKey`、`RegNtPostRenameKey` |

必须先判断通知类型，再把 `Argument2` 转换成对应结构。不能用同一种结构解析所有注册表通知。:chatgpt-content-reference{index="34"}

## Pre、Post 与状态控制

### Pre 阶段

对于正常的前置通知：

```c
return STATUS_SUCCESS;
```

表示本过滤器允许操作继续处理，并不保证操作最终成功。

返回一个使 `NT_SUCCESS(status)` 为假的状态，例如：

```c
return STATUS_ACCESS_DENIED;
```

可以阻止当前注册表操作。该操作被前置拒绝后，不会再发生对应的后置通知，因此不能把所有资源释放和拒绝日志都放到 Post 中等待执行。:chatgpt-content-reference{index="35"}

### Post 阶段

Post 用于处理操作完成后的信息，但注册表 Post 不能简单归类为“永远只读”。

在文档规定的场景下，过滤器可以修改输出参数，或者修改 `REG_POST_OPERATION_INFORMATION.ReturnStatus` 并返回 `STATUS_CALLBACK_BYPASS`。这要求同步正确处理输出和资源所有权，不能只修改一个状态码而忽略已经产生的对象或结果。:chatgpt-content-reference{index="36"}

`STATUS_CALLBACK_BYPASS` 也不是“拒绝访问”的别名。前置返回该状态时，表示过滤器自行接管并完成了操作，需要提供正确的输出，而不是简单让系统放弃处理。

## 注册表键名称与对象有效性

通知中经常拿到的是键对象，而不是直接拿到 `HKLM\...` 形式的完整字符串。

`CmCallbackGetKeyObjectIDEx` 可以根据有效的键对象取得键标识和名称；取得的名称需要通过 `CmCallbackReleaseKeyObjectIDEx` 释放。这组 Ex 接口从 Windows 8 开始提供。:chatgpt-content-reference{index="37"}

策略匹配还必须区分名称空间。例如，内核侧测试名称可以表示为：

```text
\REGISTRY\MACHINE\SOFTWARE\EdrLab
```

不能把这个字符串直接与用户界面中的 `HKLM\SOFTWARE\EdrLab` 进行无转换的比较。

对象指针也不是只要非空就有效。对于 `RegNtPostCreateKeyEx` 和 `RegNtPostOpenKeyEx`，只有当 `REG_POST_OPERATION_INFORMATION.Status == STATUS_SUCCESS` 时，`Object` 才有效；仅判断 `NT_SUCCESS(Status)` 还不够。:chatgpt-content-reference{index="38"}

注册表过滤还提供两种不同的上下文用途：

| 上下文 | 用途 |
|---|---|
| 操作的 `CallContext` | 关联某次操作的前后处理。 |
| `CmSetCallbackObjectContext` | 给键对象关联驱动自定义上下文，并处理相应清理通知。 |

操作上下文和对象上下文的生命周期不同，不能混用。:chatgpt-content-reference{index="39"}

## 限制测试注册表键的写入

下面只拒绝对指定测试键执行“设置值”操作，不包含删除、重命名、创建子键等其他保护策略。

```c
UNICODE_STRING gProtectedKey =
    RTL_CONSTANT_STRING(
        L"\\REGISTRY\\MACHINE\\SOFTWARE\\EdrLab"
    );

NTSTATUS OnRegistryNotify(
    PVOID CallbackContext,
    PVOID Argument1,
    PVOID Argument2
)
{
    REG_NOTIFY_CLASS notifyClass =
        (REG_NOTIFY_CLASS)(ULONG_PTR)Argument1;

    if (notifyClass != RegNtPreSetValueKey) {
        return STATUS_SUCCESS;
    }

    PREG_SET_VALUE_KEY_INFORMATION info =
        (PREG_SET_VALUE_KEY_INFORMATION)Argument2;

    PCUNICODE_STRING keyName = NULL;

    NTSTATUS status = CmCallbackGetKeyObjectIDEx(
        &gRegistryCookie,
        info->Object,
        NULL,
        &keyName,
        0
    );

    if (!NT_SUCCESS(status)) {
        // 示例采用名称解析失败时放行，并记录失败计数。
        ...
        return STATUS_SUCCESS;
    }

    BOOLEAN deny = RtlEqualUnicodeString(
        keyName,
        &gProtectedKey,
        TRUE
    );

    // 如需上报键名或值名，应在这里安全复制所需数据。
    ...

    CmCallbackReleaseKeyObjectIDEx(keyName);

    return deny
        ? STATUS_ACCESS_DENIED
        : STATUS_SUCCESS;
}

NTSTATUS RegisterRegistryMonitor(
    PDRIVER_OBJECT DriverObject,
    PCUNICODE_STRING Altitude
)
{
    return CmRegisterCallbackEx(
        OnRegistryNotify,
        Altitude,
        DriverObject,
        NULL,
        &gRegistryCookie,
        NULL
    );
}
```

这里显式选择了名称解析失败时放行，即 *fail-open*。实际产品必须为名称查询失败、内存不足等情况制定策略，而不是让辅助函数的错误路径意外决定系统是否被全局阻断。

注册表通知中的缓冲区和嵌套指针还需要遵守各结构及目标系统版本的访问规则。把相关指针直接保存到工作线程，或者在回调中不加限制地再次发起注册表操作，都可能产生生命周期或重入问题。:chatgpt-content-reference{index="40"}

# 文件系统过滤

现代文件系统过滤通常使用 Minifilter 模型，由 `FltMgr.sys` 管理过滤驱动与文件系统之间的交互。它与自行维护传统文件系统过滤附加链的 Legacy Filter 模型不同。:chatgpt-content-reference{index="41"}

## FltMgr、实例与高度

Minifilter 中需要区分三个对象：

| 对象 | 含义 |
|---|---|
| Filter | 已注册的过滤驱动。 |
| Instance | 过滤驱动附加到某个卷上的实例。 |
| Altitude | 实例在过滤栈中的相对位置。 |

因此：

> 驱动加载成功，不等于过滤器注册成功；过滤器注册成功，也不等于已经附加到需要监控的卷。

文件 I/O 的 Pre 通常按照从高到低的实例高度经过过滤器，Post 则沿相反方向返回。这个排序属于文件系统过滤栈，不能据此推导它与 Ps、Ob 或 WFP 回调之间的统一执行顺序。:chatgpt-content-reference{index="42"}

## I/O 操作与返回状态

Minifilter 通过 `FLT_OPERATION_REGISTRATION` 指定需要参与的 I/O 类型。

| 操作类型 | 典型用途 |
|---|---|
| `IRP_MJ_CREATE` | 文件或目录的打开、创建。 |
| `IRP_MJ_READ` | 读取数据。 |
| `IRP_MJ_WRITE` | 写入数据。 |
| `IRP_MJ_SET_INFORMATION` | 重命名、删除处置及其他信息修改场景。 |
| `IRP_MJ_CLEANUP`、`IRP_MJ_CLOSE` | 句柄清理与对象关闭相关处理。 |

`IRP_MJ_CREATE` 中的 Create 不只是“新建一个磁盘文件”，打开已有文件也会经过这一类操作。Minifilter 只会收到自己注册的操作类型，因此只注册 Create 不能自然获得完整的读写监控能力。:chatgpt-content-reference{index="43"}

Pre 回调的返回值决定接下来如何流转：

| 返回值 | 含义 |
|---|---|
| `FLT_PREOP_SUCCESS_NO_CALLBACK` | 继续处理，不要求调用本过滤器的 Post。 |
| `FLT_PREOP_SUCCESS_WITH_CALLBACK` | 继续处理，并要求调用已注册的 Post。 |
| `FLT_PREOP_COMPLETE` | 本过滤器完成操作，需要设置最终 `IoStatus`。 |
| `FLT_PREOP_PENDING` | 在受支持的 IRP 路径挂起操作，之后必须完成。 |
| `FLT_PREOP_DISALLOW_FASTIO` | 不允许当前 Fast I/O 路径，不等于直接拒绝整个文件操作。 |

返回 `FLT_PREOP_COMPLETE` 后，操作不会继续下发到更低的过滤器或文件系统，也不会调用本过滤器自己的 Post；已经经过的更高层过滤器仍可能收到 Post。Cleanup 和 Close 操作不能被设置为失败。:chatgpt-content-reference{index="44"}

## 文件打开拦截

下面示例查询文件名称，并阻止打开指定实验文件。它是路径匹配演示，不是完整的文件自保护方案。

```c
FLT_PREOP_CALLBACK_STATUS OnPreCreate(
    PFLT_CALLBACK_DATA Data,
    PCFLT_RELATED_OBJECTS FltObjects,
    PVOID* CompletionContext
)
{
    *CompletionContext = NULL;

    PFLT_FILE_NAME_INFORMATION nameInfo = NULL;

    NTSTATUS status = FltGetFileNameInformation(
        Data,
        FLT_FILE_NAME_NORMALIZED |
        FLT_FILE_NAME_QUERY_DEFAULT,
        &nameInfo
    );

    if (!NT_SUCCESS(status)) {
        // 示例采用名称查询失败时放行。
        ...
        return FLT_PREOP_SUCCESS_NO_CALLBACK;
    }

    BOOLEAN deny = IsLabDeniedFileName(&nameInfo->Name);

    FltReleaseFileNameInformation(nameInfo);

    if (!deny) {
        return FLT_PREOP_SUCCESS_NO_CALLBACK;
    }

    Data->IoStatus.Status = STATUS_ACCESS_DENIED;
    Data->IoStatus.Information = 0;

    return FLT_PREOP_COMPLETE;
}

const FLT_OPERATION_REGISTRATION gFileOperations[] = {
    { IRP_MJ_CREATE, 0, OnPreCreate, NULL },
    { IRP_MJ_OPERATION_END }
};
```

`FltGetFileNameInformation` 并不是在任何执行上下文中都可以随意调用的字符串查询函数，其行为受 I/O 类型、缓存和当前上下文限制。名称查询失败应单独记录，不能悄悄等价为“文件不受保护”。:chatgpt-content-reference{index="45"}

注册和开始过滤是两个步骤：

```c
FLT_REGISTRATION gFilterRegistration = {0};

NTSTATUS RegisterFileMonitor(PDRIVER_OBJECT DriverObject)
{
    // 全局策略、锁和队列必须已经就绪。
    ...

    gFilterRegistration.Size =
        sizeof(FLT_REGISTRATION);
    gFilterRegistration.Version =
        FLT_REGISTRATION_VERSION;
    gFilterRegistration.OperationRegistration =
        gFileOperations;
    gFilterRegistration.FilterUnloadCallback =
        OnFilterUnload;  // 接入统一退出流程

    NTSTATUS status = FltRegisterFilter(
        DriverObject,
        &gFilterRegistration,
        &gFilter
    );

    if (!NT_SUCCESS(status)) {
        return status;
    }

    status = FltStartFiltering(gFilter);

    if (!NT_SUCCESS(status)) {
        FltUnregisterFilter(gFilter);
        gFilter = NULL;
    }

    return status;
}
```

**`FltStartFiltering` 返回之前，就可能已经发生回调。** 因此不能在它成功返回后才初始化回调使用的策略或队列。:chatgpt-content-reference{index="46"}

## 文件过滤的覆盖范围

上面的示例只控制新的文件打开请求。它没有自动解决已有文件句柄上的写入，也没有覆盖所有重命名、内存映射、缓存和分页 I/O 场景。

设计文件保护时，应先明确要控制的是“打开某个路径”“修改某个文件对象”，还是“禁止某类内容写入”。这些目标需要不同的操作注册、身份识别和测试路径，不能仅靠一个文件名字符串判断替代整个方案。

Post 阶段得到失败状态，也不等于可以把所有已经发生的文件系统副作用自动回滚。返回状态控制和数据恢复是不同的问题。

## 挂起操作与完成责任

`FLT_PREOP_PENDING` 只适用于受支持的 IRP 操作。返回后，驱动必须在后续路径调用 `FltCompletePendedPreOperation`，才能让处理继续或结束。:chatgpt-content-reference{index="47"}

一个完整挂起设计至少应明确：

```text
接收操作
    ↓
进入挂起状态
    ├─ 正常裁决完成
    ├─ 超时
    ├─ 请求取消
    └─ 驱动准备卸载
    ↓
由唯一的完成路径结束操作
```

这些分支需要避免重复完成，也不能遗漏完成。卸载时尤其不能先销毁工作线程，再等待依赖该线程完成的挂起 I/O。

Post 回调还可能收到 `FLTFL_POST_OPERATION_DRAINING`。此时应按照框架要求清理上下文，而不是继续执行正常的业务处理逻辑。:chatgpt-content-reference{index="48"}

# 网络过滤

WFP，即 Windows Filtering Platform，提供不同网络处理阶段的过滤能力。

对于仅依据内置条件进行固定允许或阻断的规则，可以直接使用 WFP 过滤器；需要自定义内核判断或数据处理时，再引入 Callout 驱动。下面刻意使用 Callout，以展示驱动接入流程。:chatgpt-content-reference{index="49"}

## Layer、Filter、Callout 与 Sublayer

| 对象 | 作用 |
|---|---|
| Layer | 指定在哪个网络处理阶段进行过滤。 |
| Filter | 定义匹配条件、动作以及所属层和子层。 |
| Callout | 提供自定义分类等处理函数。 |
| Sublayer | 组织过滤器并参与排序和策略仲裁。 |

例如：

```text
某程序发起出站连接
    ↓
到达 ALE_AUTH_CONNECT 层
    ↓
匹配某个 Filter 的应用程序条件
    ↓
Filter 的动作要求调用指定 Callout
    ↓
内核 classifyFn 根据接口规则给出处理结果
```

**只注册 Callout，并不会自动检查所有网络流量。** 必须存在适用的过滤器，通过正确的层和条件引用这个 Callout。:chatgpt-content-reference{index="50"}

## Fwps 与 Fwpm 的分工

`Fwps*` 主要提供内核运行时接口，例如：

```c
FwpsCalloutRegister0(...);
FwpsCalloutUnregisterById0(...);
```

`Fwpm*` 主要管理过滤引擎中的对象，例如：

```c
FwpmEngineOpen0(...);
FwpmSubLayerAdd0(...);
FwpmCalloutAdd0(...);
FwpmFilterAdd0(...);
```

不能把 `Fwpm*` 简化成“只能在用户态使用的 API”；部分管理接口同时提供内核态版本。本文选择由用户态服务管理策略，由驱动提供运行时 Callout。:chatgpt-content-reference{index="51"}

接口名称中的 `0`、`1`、`2` 是版本后缀。回调签名和结构版本必须配套，不能把 `FWPS_CALLOUT0` 与其他版本的分类函数参数随意混用。:chatgpt-content-reference{index="52"}

## 过滤层选择

| 层 | 主要用途 |
|---|---|
| `ALE_AUTH_CONNECT_V4/V6` | 出站连接授权等场景，常用于按应用控制新连接。 |
| `ALE_AUTH_RECV_ACCEPT_V4/V6` | 入站接收或连接接受授权。 |
| `ALE_FLOW_ESTABLISHED_V4/V6` | 流建立后的关联和跟踪。 |
| `STREAM_V4/V6` | TCP 数据流处理。 |
| `DATAGRAM_DATA_V4/V6` | 数据报处理，常见于 UDP 场景。 |
| Transport / IP Packet 相关层 | 更接近传输层或 IP 数据包的处理。 |

层越靠近数据包，并不意味着越适合识别应用行为。能获取什么字段、`layerData` 是什么结构、哪些元数据有效，都由当前层决定。:chatgpt-content-reference{index="53"}

例如，读取进程 ID 前，应检查：

```c
Meta->currentMetadataValues & FWPS_METADATA_FIELD_PROCESS_ID
```

不能假定每个层都提供进程 ID，也不能把当前执行分类函数的线程所属进程直接当成网络连接的发起者。:chatgpt-content-reference{index="54"}

## 注册内核运行时 Callout

下面使用版本 `0` 的接口。其分类函数是六个参数，没有其他版本中的额外 `classifyContext` 参数。

这个 Callout 专门服务于实验阻断规则：只要匹配到引用它的规则，且拥有动作写入权限，就返回阻断。

```c
VOID OnLabClassify(
    const FWPS_INCOMING_VALUES0* FixedValues,
    const FWPS_INCOMING_METADATA_VALUES0* Meta,
    VOID* LayerData,
    const FWPS_FILTER0* Filter,
    UINT64 FlowContext,
    FWPS_CLASSIFY_OUT0* Out
)
{
    if ((Out->rights & FWPS_RIGHT_ACTION_WRITE) == 0) {
        return;
    }

    Out->actionType = FWP_ACTION_BLOCK;
    Out->rights &= ~FWPS_RIGHT_ACTION_WRITE;

    ...
}

NTSTATUS OnLabCalloutNotify(
    FWPS_CALLOUT_NOTIFY_TYPE NotifyType,
    const GUID* FilterKey,
    FWPS_FILTER0* Filter
)
{
    ...
    return STATUS_SUCCESS;
}

NTSTATUS RegisterNetworkMonitor(PDEVICE_OBJECT DeviceObject)
{
    FWPS_CALLOUT0 callout = {0};

    callout.calloutKey = EDRLAB_CONNECT_V4_CALLOUT_KEY;
    callout.classifyFn = OnLabClassify;
    callout.notifyFn = OnLabCalloutNotify;

    // 本示例没有为网络流关联自定义 flow context。
    callout.flowDeleteFn = NULL;

    return FwpsCalloutRegister0(
        DeviceObject,
        &callout,
        &gRuntimeCalloutId
    );
}
```

这里的 `DeviceObject` 必须是驱动已经创建的设备对象。返回的运行时标识需要保存，以供后续注销使用。:chatgpt-content-reference{index="55"}

`FWP_ACTION_BLOCK` 配合清除动作写入权限，是这个示例的裁决方式。`FWP_ACTION_CONTINUE` 则表示继续交给后续过滤处理，不等于“这条连接最终一定放行”。多个过滤器之间还存在策略仲裁规则。:chatgpt-content-reference{index="56"}

## 配置管理面与匹配条件

示例服务使用动态 WFP 会话：

```text
FwpmEngineOpen0
    ↓
FwpmTransactionBegin0
    ↓
FwpmSubLayerAdd0
    ↓
FwpmCalloutAdd0
    ↓
FwpmFilterAdd0
    ↓
FwpmTransactionCommit0
```

运行时 Callout 和管理面 Callout 必须使用同一个 `calloutKey`。管理面 Callout 的 `applicableLayer`、Filter 的 `layerKey`，也必须与示例设计对应。官方推荐的建立顺序是先注册运行时 Callout，再添加管理对象和引用它的 Filter。:chatgpt-content-reference{index="57"}

下面展示 `service/wfp_policy.cpp` 的核心逻辑。前提是：

`Engine` 已通过带 `FWPM_SESSION_FLAG_DYNAMIC` 的会话打开；`AppId` 是为实验程序取得的 WFP 应用标识；两个 `EDRLAB_*_KEY` 是本项目定义的 GUID。

```cpp
DWORD InstallLabConnectRule(
    HANDLE Engine,
    FWP_BYTE_BLOB* AppId
)
{
    wchar_t name[] = L"EdrLab";

    FWPM_SUBLAYER0 sublayer{};
    sublayer.subLayerKey = EDRLAB_SUBLAYER_KEY;
    sublayer.displayData.name = name;
    sublayer.weight = 0x100;  // 仅为实验选择的子层权重

    FWPM_CALLOUT0 callout{};
    callout.calloutKey = EDRLAB_CONNECT_V4_CALLOUT_KEY;
    callout.displayData.name = name;
    callout.applicableLayer = FWPM_LAYER_ALE_AUTH_CONNECT_V4;

    FWPM_FILTER_CONDITION0 condition{};
    condition.fieldKey = FWPM_CONDITION_ALE_APP_ID;
    condition.matchType = FWP_MATCH_EQUAL;
    condition.conditionValue.type = FWP_BYTE_BLOB_TYPE;
    condition.conditionValue.byteBlob = AppId;

    FWPM_FILTER0 filter{};
    filter.displayData.name = name;
    filter.layerKey = FWPM_LAYER_ALE_AUTH_CONNECT_V4;
    filter.subLayerKey = EDRLAB_SUBLAYER_KEY;
    filter.weight.type = FWP_EMPTY;
    filter.numFilterConditions = 1;
    filter.filterCondition = &condition;
    filter.action.type = FWP_ACTION_CALLOUT_TERMINATING;
    filter.action.calloutKey = EDRLAB_CONNECT_V4_CALLOUT_KEY;

    DWORD error = FwpmTransactionBegin0(Engine, 0);
    if (error != ERROR_SUCCESS) {
        return error;
    }

    error = FwpmSubLayerAdd0(Engine, &sublayer, nullptr);
    if (error != ERROR_SUCCESS) {
        goto rollback;
    }

    error = FwpmCalloutAdd0(Engine, &callout, nullptr, nullptr);
    if (error != ERROR_SUCCESS) {
        goto rollback;
    }

    error = FwpmFilterAdd0(Engine, &filter, nullptr, nullptr);
    if (error != ERROR_SUCCESS) {
        goto rollback;
    }

    error = FwpmTransactionCommit0(Engine);
    if (error == ERROR_SUCCESS) {
        return error;
    }

rollback:
    FwpmTransactionAbort0(Engine);
    return error;
}
```

用户态 `Fwpm*` 接口这里返回的是 `DWORD` 错误码，应比较 `ERROR_SUCCESS`，不能套用内核 `NTSTATUS` 的判断方式。事务内某次添加失败，也不意味着整个事务已经自动回滚，需要显式处理。:chatgpt-content-reference{index="58"}

该规则只匹配指定实验程序的 IPv4 出站授权，不是整个系统的通用断网规则。IPv6 需要对应层和规则，不能因为 IPv4 测试成功就判定双栈覆盖完成。

## 连接生命周期与策略撤销

动态会话中的管理对象会在会话结束时自动删除。因此，服务成功安装规则后，应在策略需要生效期间保持会话，而不是立即关闭引擎句柄。动态会话结束也不会替代内核的 `FwpsCalloutUnregisterById0`。:chatgpt-content-reference{index="59"}

卸载时需要分开处理：

```text
不再需要的管理面 Filter
    ↓
管理面 Callout、Sublayer 等对象
    ↓
运行时 Callout
    ↓
驱动设备与自身资源
```

具体实现还需要结合并发和流上下文处理。运行时 Callout 注销后，如果仍有终止型过滤器引用它，过滤器可能被按阻断处理，而不是自动失效放行。不能把“驱动停止了”与“网络恢复原状”画等号。:chatgpt-content-reference{index="60"}

如果为网络流关联了上下文，`FwpsCalloutUnregisterById0` 可能返回 `STATUS_DEVICE_BUSY`。应移除相关流上下文并再次完成注销，不能忽略失败后直接卸载驱动。:chatgpt-content-reference{index="61"}

还应区分新连接控制和已有连接控制。在授权层拒绝新的连接尝试，不等于立即终止所有已经建立的连接。TCP 数据流检查、已有流处理和连接授权需要分别设计，不能用一个“网络阻断”布尔值替代所有状态。

# 其他内核通知

除了前述 EDR 常用入口，Windows 还提供一些辅助通知机制。它们应按所属领域理解，不应因为都带有 `Register` 或 `Callback` 就视为同一种 Hook。

| 接口 | 关注范围 | 对应退出方式或限制 |
|---|---|---|
| `ExRegisterCallback` | 在回调对象上注册通知，属于回调对象机制。 | `ExUnregisterCallback`；不是对所有 `Ex*` 函数的拦截。 |
| `IoRegisterPlugPlayNotification` | 即插即用相关事件。 | `IoUnregisterPlugPlayNotificationEx` 等对应接口。 |
| `IoRegisterFsRegistrationChange` | 文件系统注册状态变化，主要与传统文件系统过滤场景有关。 | `IoUnregisterFsRegistrationChange`；不是每次文件访问通知。 |
| `PoRegisterPowerSettingCallback` | 电源设置变化。 | `PoUnregisterPowerSettingCallback`。 |
| `SeRegisterLogonSessionTerminatedRoutine` | 登录会话终止。 | 会话关联的最后一个令牌引用消失才满足终止条件，不能简单等同于用户点击注销。 |
| `IoRegisterShutdownNotification` | 为设备登记系统关闭处理。 | 接收 `IRP_MJ_SHUTDOWN`，不是直接注册普通函数指针。 |
| `KeRegisterBugCheckReasonCallback` | 系统崩溃相关的有限处理。 | `KeDeregisterBugCheckReasonCallback`；不适合作为正常业务事件处理入口。 |

这些接口分别由执行体、I/O、电源、安全和内核崩溃处理机制管理。它们可以辅助产品生命周期管理，但不能替代 Ps、Ob、Cm、Minifilter 或 WFP 的主要监控职责。:chatgpt-content-reference{index="62"}

# 回调执行与驱动生命周期

## IRQL 与线程上下文

IRQL 是内核执行约束的一部分，不能把它简单理解成普通线程优先级。某个函数允许在 `PASSIVE_LEVEL` 执行，也不意味着当前回调可以安全地进行任意阻塞、递归调用或用户态通信。

需要分别检查“注册 API 的调用条件”和“注册后回调的执行条件”。

| 回调 | 主要执行约束 |
|---|---|
| 进程 Ex 通知 | `PASSIVE_LEVEL`，处于临界区，普通内核 APC 被禁用。 |
| 普通线程通知 | 可能在 `PASSIVE_LEVEL` 或 `APC_LEVEL`。 |
| 镜像加载通知 | `PASSIVE_LEVEL`，同时受到临界区和 APC 等约束。 |
| Ob Pre / Post | `PASSIVE_LEVEL`，普通内核 APC 被禁用。 |
| 注册表回调 | 不高于 `APC_LEVEL`，还需遵循通知数据与重入规则。 |
| Minifilter Pre | 可能为 `PASSIVE_LEVEL` 或 `APC_LEVEL`，上下文依 I/O 路径而定。 |
| Minifilter Post | 可能在 `DISPATCH_LEVEL`，不能假设可以执行所有 Pre 中的操作。 |
| WFP `classifyFn` | 可能达到 `DISPATCH_LEVEL`，需要按当前层和数据类型处理。 |

这些限制直接影响可分页内存、锁、工作项和可调用 API 的选择。:chatgpt-content-reference{index="63"}

例如，文件 Pre 回调可能运行在上层过滤器派发的系统工作线程中。此时“当前进程”不一定就是最初发起文件操作的应用程序。事件归因应使用对应框架提供的语义信息，而不是在所有回调中统一调用一次“取得当前 PID”。:chatgpt-content-reference{index="64"}

## 同步裁决与异步上报

建议把两条路径分开设计：

```text
同步裁决路径
事件到达 → 读取本地策略快照 → 给出当前节点允许的处理结果 → 返回

异步上报路径
事件到达 → 复制必要字段 → 放入有界队列 → 工作线程/服务消费
```

这里的“异步”是产品架构设计，不代表所有操作都可以先返回、之后再否决。一个 Ps 或 Ob 回调已经返回后，用户态服务稍后得出的结论，不能被当作该次回调的同步阻断结果。

微软明确要求相关进程、线程、镜像和对象通知尽量短小，避免等待用户态服务或其他工作线程。:chatgpt-content-reference{index="65"}

事件队列应保存自己拥有的数据，而不是回调参数的借用指针。需要长期保留对象时，还必须遵循对应对象和框架的引用规则；并非每个看起来像内核对象的指针，都能在任何通知阶段安全地增加引用。注册表键销毁相关通知就是需要特别谨慎的例子。:chatgpt-content-reference{index="66"}

作为本项目的事件协议，可以考虑包含：

```text
事件类别
事件时间与本地序号
实际执行上下文信息
目标进程、线程或资源标识
原始请求和本地裁决
策略版本
采集失败或字段缺失标志
```

“字段不存在”“查询失败”和“值为空”应使用不同表示方式，否则后续分析容易把缺失数据误解释为正常行为。

## 初始化与失败回滚

初始化应先准备好回调所依赖的共享状态，再开放事件入口。

```text
初始化策略、锁、队列和停止状态
    ↓
按依赖关系注册各功能模块
    ↓
启用控制接口和正常事件消费
```

每个模块应记录自己的注册结果，不能只设置一个笼统的 `Initialized = TRUE`。

例如，Ps 和 Ob 注册成功、Cm 注册失败时，驱动需要撤销已经成功的注册。失败回滚应处理“已经成功建立的资源”，不能调用一批未初始化句柄对应的清理函数。

文件过滤开始后可能立即回调，WFP 管理对象又可能在运行时 Callout 不存在时产生阻断效果，因此初始化顺序本身也是功能和可用性的一部分。:chatgpt-content-reference{index="67"}

## 注册与注销配对

| 注册入口 | 对应注销方式 | 需要保存的信息 |
|---|---|---|
| `PsSetCreateProcessNotifyRoutine*` | 使用对应注册接口，设置 `Remove = TRUE`。 | 原回调函数；Ex2 还需匹配通知类型。 |
| `PsSetCreateThreadNotifyRoutine*` | `PsRemoveCreateThreadNotifyRoutine` | 原回调函数。 |
| `PsSetLoadImageNotifyRoutine*` | `PsRemoveLoadImageNotifyRoutine` | 原回调函数。 |
| `ObRegisterCallbacks` | `ObUnRegisterCallbacks` | 注册句柄。 |
| `CmRegisterCallbackEx` | `CmUnRegisterCallback` | 注册 Cookie。 |
| `FltRegisterFilter` | `FltUnregisterFilter` | `PFLT_FILTER`。 |
| `FwpsCalloutRegister0` | `FwpsCalloutUnregisterById0` 或对应 Key 接口。 | 运行时 ID 或 Key。 |

这里的 `*` 是接口族简写，不是可以直接编译的函数名。进程通知不存在一个与线程通知完全对称的通用 `PsRemoveCreateProcessNotifyRoutine` 用法。:chatgpt-content-reference{index="68"}

进程 Ex 通知注销会等待正在执行的回调完成，不能在自身回调中执行该注销。注册表回调也不能在自身回调中调用注销来“立即移除自己”，否则可能死锁。:chatgpt-content-reference{index="69"}

## 卸载与资源排空

卸载不是“调用几个 Unregister 后直接返回”。

一个完整的退出方案需要处理：

```text
进入停止状态
    ↓
拒绝新的控制请求，阻止新的自有任务继续入队
    ↓
按框架要求停止事件来源，并处理挂起操作
    ↓
等待已进入的回调与自有工作项结束
    ↓
释放对象引用、队列、通信端口和设备
    ↓
完成卸载
```

其中“停止事件来源”和“完成挂起操作”的具体先后关系，需要服从对应框架，不能机械地套用一个全局逆序。

特别是：

**注销回调不等于排空自建事件队列。** 即使框架已经不再调用回调，工作线程仍可能持有驱动分配的数据。

**注销失败不等于可以强行释放代码。** WFP 存在关联流上下文时就可能拒绝完成注销。:chatgpt-content-reference{index="70"}

**Minifilter 需要通过其卸载回调接入退出流程。** 如果一个实验驱动同时包含多个模块，应把整体清理协调到正确的卸载路径，避免普通驱动退出路径与过滤器退出路径互相遗漏或重复释放。:chatgpt-content-reference{index="71"}

## 用户态通信边界

用户态服务与驱动之间可以设计设备控制接口；Minifilter 还提供通信端口机制。通信协议本身需要进行访问控制、长度检查和状态校验，而不是默认本机调用者都可信。:chatgpt-content-reference{index="72"}

驱动不应为了方便调试而向任意用户态调用者提供通用内核地址读写、任意函数调用等能力。一个功能正确的 EDR 监控驱动，如果控制接口缺少约束，仍可能成为系统中的高权限漏洞入口。:chatgpt-content-reference{index="73"}

# 运行与验证

## 实验使用路径

前述代码是核心逻辑片段。实际验证前，需要补齐驱动工程、签名、安装、配置、事件消费和测试程序。

可以采用以下实验对象：

```text
LabTarget.exe：被创建、被访问、被保护的目标进程。
LabCaller.exe：申请或复制目标句柄的调用方。
LabClient.exe：发起网络连接的实验客户端。

注册表测试键：
\REGISTRY\MACHINE\SOFTWARE\EdrLab

文件测试对象：
独立实验目录中的指定文件。
```

先在不启用阻断策略时建立基线，再逐项启用规则。不要同时打开所有阻断条件后，仅通过“某个程序不能运行”判断功能是否正确。

以下是设计的验证输入和预期断言，不是本文已经执行得到的测试结果。

| 测试输入 | 应验证的结果 |
|---|---|
| 正常启动并退出 `LabTarget.exe` | 进程创建和退出信息能够正确关联，创建者与父进程字段分别保存。 |
| 启用进程创建拒绝规则后启动目标 | 创建被否决，并能看到本地设置的创建状态；不能把回调返回类型写错。 |
| 对已经运行的目标调用 `OpenProcess` | 出现句柄授权事件，但不会因此重新出现目标进程创建事件。 |
| 复制一个指向目标进程的句柄 | 区分源句柄表进程、接收句柄的进程和句柄真正指向的目标。 |
| 获取权限被裁剪的句柄 | 即使句柄获取成功，依赖被移除权限的操作仍应失败。 |
| 使用策略启用前获得的句柄 | 单独验证已有授权，不把它与新句柄过滤效果混为一谈。 |
| 设置受保护测试键的值 | 前置拒绝后，测试值不被该操作修改，也不能等待对应 Post 才记录拒绝。 |
| 打开指定实验文件 | 在目标卷实例已附加、名称匹配成功的前提下，被 Create 前置逻辑拒绝。 |
| `LabClient.exe` 发起新的 IPv4 连接 | 命中指定 WFP Filter 和 Callout；IPv6 与已有连接分别验证。 |
| 撤销动态网络策略 | 管理对象被移除，并验证没有遗留过滤器继续影响网络。 |

这些测试分别针对接口的生命周期、授权和完成语义，而不是简单比较“有没有日志”。:chatgpt-content-reference{index="74"}

## 检查文件过滤与网络规则

在管理员终端中，可以检查已经安装并加载的实验 Minifilter：

```powershell
fltmc filters
fltmc instances
fltmc volumes
```

`filters` 用于查看过滤器，`instances` 用于确认实例附加状态。过滤器出现在列表中，而目标卷没有相应实例时，应先检查附加和配置，而不是立即判断回调失效。:chatgpt-content-reference{index="75"}

WFP 可以导出当前状态：

```powershell
netsh wfp show state file=wfpstate.xml
```

应检查 Filter、Layer、Sublayer、Callout Key 和应用匹配条件是否符合实验设计。运行时注册成功和管理面规则正确，是两个不同的检查点。:chatgpt-content-reference{index="76"}

## 覆盖缺口与防护边界

测试中出现“行为发生但没有预期事件”时，应按机制逐层定位：

| 检查层次 | 需要回答的问题 |
|---|---|
| 注册 | 注册调用是否真正成功，失败状态是否被忽略？ |
| 附加或规则生效 | Minifilter 是否附加到目标卷，WFP 是否存在正确的匹配规则？ |
| 语义覆盖 | 当前行为是否属于这个回调负责的事件类型？ |
| 生命周期 | 操作是否发生在注册之前，是否使用已经持有的资源？ |
| 采集 | 字段查询、缓冲区复制或事件分配是否失败？ |
| 上报 | 队列是否溢出，服务是否断开，事件是否被丢弃？ |
| 策略 | 是否命中了错误对象、错误名称空间或过期策略？ |

“没有日志”不能直接证明“内核回调被绕过”。同样，“驱动已经加载”也不能证明所有目标行为都已覆盖。

驱动层监控也不是不可破坏的最终信任根。Windows x64 内核保护和内存完整性机制可以限制部分代码与数据破坏路径，但这不意味着每个已签名驱动都没有漏洞，也不意味着某个 Ob 回调就能独立解决所有进程自保护问题。:chatgpt-content-reference{index="77"}

## 并发、异常与卸载测试

功能正确之后，还应验证以下工程场景：

| 场景 | 重点断言 |
|---|---|
| 大量并发进程、线程和句柄操作 | 没有竞态、长时间锁竞争或不可控内存增长。 |
| 队列达到上限 | 存在明确丢弃策略和计数，不因采集失败导致系统无限等待。 |
| 用户态服务退出或重启 | 内核行为符合既定失败策略，不出现无期限阻塞。 |
| 任意一个模块注册失败 | 已成功模块被完整回滚，没有残留回调和过滤对象。 |
| 文件操作挂起期间卸载 | 挂起请求被完成或取消，不重复完成，也不永远挂起。 |
| 网络流上下文仍存在时注销 | 正确处理忙状态，不在 Callout 仍被使用时释放驱动。 |
| 反复加载、卸载和策略切换 | 不出现重复注册、对象泄漏、旧策略引用和悬空指针。 |

在可恢复的测试虚拟机中，可以只对自己的实验驱动启用 Driver Verifier：

```powershell
verifier /standard /driver EdrLab.sys
```

按要求重启后运行测试，并检查配置：

```powershell
verifier /querysettings
```

实验结束时清除配置：

```powershell
verifier /reset
```

随后重启，使重置后的配置生效。Verifier 的目标是暴露驱动错误；出现蓝屏时应结合转储定位违规路径，而不是把“能正常加载”作为稳定性验证的终点。:chatgpt-content-reference{index="78"}
