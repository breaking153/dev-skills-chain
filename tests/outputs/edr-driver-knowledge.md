# 概念

EDR 的驱动层组件利用 Windows 在进程生命周期、对象句柄、注册表、文件 I/O 和网络处理中的扩展点采集行为，并在接口允许的阶段执行访问控制。本文以 Windows x64 的公开驱动接口为范围，说明各机制的对象、控制能力、执行约束与资源生命周期。

## Hook、通知回调与过滤框架

狭义 Hook 通过修改函数入口、分发表等位置改变原有执行路径。Windows x64 对内核代码和部分关键数据结构实施保护，修改受保护区域可能导致系统错误；本文不涉及内核补丁、未公开回调数组或第三方驱动内部结构。

通知回调由驱动向系统登记函数，在受支持的事件发生时由对应子系统调用。例如，`PsSetCreateProcessNotifyRoutineEx` 注册进程创建和退出通知，系统仍按原有进程创建流程运行，并在约定节点通知驱动。

回调的控制能力取决于接口契约：进程创建 Ex 通知允许修改创建状态；线程和镜像通知提供观测信息；对象回调允许限制特定句柄权限。文件系统与网络则提供专门的过滤框架，管理多个处理阶段及其对象、排序和完成责任。

| 接口族或框架 | 关注对象 | 典型能力 |
|---|---|---|
| `Ps*` | 进程、线程生命周期和镜像加载 | 采集通知；进程创建 Ex 回调可否决创建。 |
| `Ob*` | 支持的对象类型的句柄创建与复制 | 在 Pre 阶段削减文档允许修改的访问权限。 |
| `Cm*` | 注册表操作 | 在 Pre 阶段阻断，或按规则处理输出与返回状态。 |
| Minifilter / `Flt*` | 文件系统 I/O | 参与请求下发与完成，支持放行、完成及特定路径的挂起。 |
| WFP / `Fwps*`、`Fwpm*` | 网络授权、流和数据包 | 配置允许、阻断规则，或由内核 Callout 自定义处理。 |

这些机制共同构成内核侧的观测与控制面。`Ps`、`Ob`、`Cm` 是子系统命名前缀，其下还包含查询和管理函数，具体职责应落实到 API。

## 内核对象、句柄与访问权限

进程对象表示内核维护的进程实体；进程句柄是某个句柄表中引用该对象的入口，并携带访问权限。同一调用方可以持有多个指向同一进程对象、权限不同的句柄：一个只允许查询，另一个还允许终止进程。写内存、创建线程等操作也各自要求对应权限。

因此，EDR 需要分别记录目标进程的生命周期，以及调用方取得了怎样的访问权限。`Ps*` 描述进程正在创建或退出；`Ob*` 描述句柄正在创建或复制。使用已获得的句柄执行操作属于后续行为，通常不会重新经历一次句柄授权。

# 开发环境

示例选择 Windows 11 x64 测试虚拟机。驱动开发使用配套的 Visual Studio、Windows SDK 和 WDK，工具组合及 SDK/WDK 构建版本应按目标环境的支持要求匹配。驱动加载还取决于签名、测试签名策略和当前代码完整性配置。

实验环境应支持快照恢复。Driver Verifier 会主动暴露违规行为并可能触发蓝屏，适合在独立测试虚拟机中验证自己的实验驱动。

下文代码是未编译、未运行的机制片段，不构成可部署工程。`Policy*`、`CopyAndQueue*`、`IsLab*` 等名称表示示例辅助函数；它们需自行实现本地策略查询、数据复制和失败处理。

# 项目结构

以下示意工程按功能域拆分职责，各模块可以属于同一个驱动：

```text
EdrLab/
├─ driver/
│  ├─ entry.c             # 初始化、失败回滚与统一退出
│  ├─ process.c           # 进程、线程和镜像通知
│  ├─ object.c            # 进程、线程句柄过滤
│  ├─ registry.c          # 注册表过滤
│  ├─ file.c              # Minifilter
│  ├─ network.c           # WFP 运行时 Callout
│  ├─ policy.c            # 内核本地策略快照
│  ├─ events.c            # 有界事件队列与工作项
│  └─ EdrLab.inf          # 安装与过滤实例配置
├─ shared/
│  └─ protocol.h          # 驱动与服务的数据协议
├─ service/
│  ├─ main.cpp            # 策略管理、事件消费与持久化
│  └─ wfp_policy.cpp      # WFP 管理对象和过滤器配置
└─ tests/
   ├─ process_test.cpp
   ├─ handle_test.cpp
   ├─ registry_test.cpp
   ├─ file_test.cpp
   └─ network_test.cpp
```

驱动在事件发生时完成短路径采集与本地裁决；服务负责策略更新、日志存储、信息补充和复杂分析。进程、线程、镜像和对象通知应及时返回，避免在回调中等待用户态服务或其他工作线程。具体数据所有权和退出协调见[回调执行与驱动生命周期](#回调执行与驱动生命周期)。

# 进程、线程与镜像通知

进程通知描述进程的创建与退出，线程通知描述某进程内线程的创建与删除，镜像通知描述镜像在地址空间中的映射。三类事件可以关联，但各自具有独立的对象和控制语义。

## 进程通知

### 创建信息与进程身份

以 `PsSetCreateProcessNotifyRoutineEx` 为例，回调接收 `Process`、`ProcessId` 和 `CreateInfo`。前两者标识正在创建或退出的目标进程；`CreateInfo != NULL` 表示创建，`CreateInfo == NULL` 表示退出。

| `PS_CREATE_NOTIFY_INFO` 字段 | 含义与使用条件 |
|---|---|
| `ParentProcessId` | 新进程的父进程 ID。 |
| `CreatingThreadId.UniqueProcess` / `UniqueThread` | 实际发起创建的进程与线程 ID。 |
| `FileObject` | 可执行文件对应的文件对象。 |
| `ImageFileName` | 可执行文件名称；是否完整、是否为实际打开名称需要结合标志判断。 |
| `FileOpenNameAvailable` | 为真时，`ImageFileName` 是用于打开可执行文件的准确名称；为假时可能只有部分名称。 |
| `CommandLine` | 创建命令行，不可用时为空。 |
| `CreationStatus` | 当前创建状态，可改成失败状态以否决创建。 |

父进程与实际创建者可能不同，事件模型应分别保存。通过 Ex2 接收非 Win32 子系统进程通知时，`IsSubsystemProcess` 可指示该类型，`FileObject`、`ImageFileName`、`CommandLine` 可能为空。[PS_CREATE_NOTIFY_INFO](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_ps_create_notify_info)

### 创建裁决与事件复制

`process.c` 中的核心片段：

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

    if (NT_SUCCESS(CreateInfo->CreationStatus) &&
        PolicyRejectsLabProcess(CreateInfo)) {
        CreateInfo->CreationStatus = STATUS_ACCESS_DENIED;
    }

    CopyAndQueueProcessCreate(ProcessId, CreateInfo);
}
```

回调返回类型为 `VOID`，拒绝通过修改 `CreationStatus` 生效。判断原状态后再设置失败，可以保留其他组件已有的拒绝结果。本驱动放行后，创建流程仍可能因后续检查失败。

`CreateInfo` 及其指向的数据只在回调期间保证有效；异步上报必须在返回前复制所需字段，并处理空值、复制失败和队列满的情况。[进程通知参数的有效期](https://learn.microsoft.com/en-us/previous-versions/ff542860%28v%3Dvs.85%29)

### 回调注册

| 接口 | 信息与适用范围 |
|---|---|
| `PsSetCreateProcessNotifyRoutine` | 传统创建、退出通知，没有 `CreationStatus`。 |
| `PsSetCreateProcessNotifyRoutineEx` | 提供 `PS_CREATE_NOTIFY_INFO`，允许否决创建；支持 Windows Vista SP1 / Windows Server 2008 起的系统。 |
| `PsSetCreateProcessNotifyRoutineEx2` | 通过通知类型扩展到子系统进程等场景；支持 Windows 10 1703 起的系统。 |

以 Ex 为例，`PsSetCreateProcessNotifyRoutineEx(OnProcessNotify, FALSE)` 添加注册；卸载时用同一回调和 `Remove = TRUE` 删除注册。

Ex 注册要求回调所在映像具有 `IMAGE_DLLCHARACTERISTICS_FORCE_INTEGRITY` 标志，缺失时可返回 `STATUS_ACCESS_DENIED`。MSVC 的 `/INTEGRITYCHECK` 与该标志有关，驱动仍需满足系统的签名要求。重复注册或注册数量达到系统限制也会失败，必须检查返回状态。[PsSetCreateProcessNotifyRoutineEx](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/nf-ntddk-pssetcreateprocessnotifyroutineex)

## 线程通知

`PsSetCreateThreadNotifyRoutine` 和 `PsSetCreateThreadNotifyRoutineEx` 注册线程通知。基本回调接收目标 `ProcessId`、`ThreadId` 与 `Create`：`TRUE` 表示创建，`FALSE` 表示删除。回调返回 `VOID`，没有进程创建通知那样的否决字段。

Ex 接口从 Windows 10 开始提供。普通创建通知和 `PsCreateThreadNotifyNonSystem` 模式具有不同执行上下文，后者在新线程上下文中执行创建回调。事件归因应使用参数和模式语义，不能统一把当前线程记成创建者。

线程事件可以与进程关系、句柄权限等信息关联，用于检测异常行为；其基本参数本身不包含完整调用链、内存来源或恶意性结论。

## 镜像加载通知

`PsSetLoadImageNotifyRoutine` 及其 Ex 版本注册镜像加载通知。回调接收 `FullImageName`、`ProcessId` 和 `IMAGE_INFO`，常用字段包括加载基址 `ImageBase`、大小 `ImageSize` 与 `SystemModeImage`。

通知发生在镜像映射之后、入口点执行之前。`FullImageName` 可能为空；内核驱动镜像的 `ProcessId` 为零，应与用户进程的 DLL 加载事件分别解释。

Ex 接口从 Windows 10 1709 开始提供，可以通过标志扩展不同体系结构镜像的通知覆盖。两种通知均返回 `VOID`，提供映射观测，不提供通过失败返回值拒绝加载的控制路径。

这组接口覆盖镜像加载，不覆盖所有可执行内存的修改，也没有对应的通用镜像卸载通知。实时模块清单需要其他依据补充；`PsRemoveLoadImageNotifyRoutine` 只撤销驱动自己的通知注册。

# 对象句柄过滤

`ObRegisterCallbacks` 在对象管理器处理句柄创建、复制时调用驱动，用于观察和限制这次句柄授权。它支持 Windows Vista SP1 / Windows Server 2008 起的系统，回调所在内核映像必须满足签名要求。

## 对象与操作

公开支持的对象类型包括进程 `PsProcessType`、线程 `PsThreadType`，以及 Windows 10 起支持的桌面 `ExDesktopObjectType`。文件、令牌、注册表键等对象应使用各自适用的接口。

注册操作为 `OB_OPERATION_HANDLE_CREATE` 和 `OB_OPERATION_HANDLE_DUPLICATE`，分别对应句柄创建和复制。句柄创建可以指向已有进程；此接口不提供通用句柄关闭或每次内存访问的通知。

句柄复制涉及三个独立实体。例如，进程 A 把指向进程 B 的句柄复制到进程 C：

| 字段 | 对应实体 |
|---|---|
| `Info->Object` | 被句柄引用的对象 B。 |
| `DuplicateHandleInformation.SourceProcess` | 源句柄表所属进程 A。 |
| `DuplicateHandleInformation.TargetProcess` | 新句柄表所属进程 C。 |

保护策略按 `Object` 识别被访问对象，同时记录源、目标句柄表进程以解释句柄流转。

## 回调注册

注册由操作描述和总注册描述两部分组成：

| 结构 | 关键成员 |
|---|---|
| `OB_OPERATION_REGISTRATION` | `ObjectType` 选择对象类型；`Operations` 选择创建、复制；`PreOperation`、`PostOperation` 指定处理函数。 |
| `OB_CALLBACK_REGISTRATION` | `Version` 使用匹配的注册版本；`OperationRegistrationCount` 与数组长度一致；`OperationRegistration` 指向操作数组；`Altitude` 参与排序；`RegistrationContext` 携带自定义上下文。 |

注册结构的进程类型字段使用 `PsProcessType`；回调收到的 `Info->ObjectType` 与 `*PsProcessType` 比较，两处字段指针层级不同。

`ObRegisterCallbacks` 成功后返回注册句柄，由驱动保存并交给 `ObUnRegisterCallbacks` 注销。高度冲突可能使注册失败；实验高度应显式配置，生产配置需遵循分配要求。

## 访问权限裁剪

### 请求权限与授权结果

Pre 信息中的 `OriginalDesiredAccess` 是原始请求，`DesiredAccess` 是当前待授予权限，`KernelHandle` 标记是否为内核句柄。驱动只能继续削减文档允许修改的权限，应在当前值上清位：

```c
DesiredAccess &= ~RightsToRemove;
```

从 `OriginalDesiredAccess` 重建权限可能恢复其他过滤器已经移除的位。文档允许修改的进程权限包括 `PROCESS_TERMINATE`、`PROCESS_CREATE_THREAD`、`PROCESS_VM_OPERATION` 和 `PROCESS_VM_WRITE` 等；其列表未包含 `PROCESS_VM_READ`，因此裁剪集合必须按结构文档选择。[OB_PRE_CREATE_HANDLE_INFORMATION](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-_ob_pre_create_handle_information)

### Pre 与 Post 的职责

Pre 回调返回 `OB_PREOP_SUCCESS`，限制通过修改 `DesiredAccess` 生效。系统仍可能成功返回一个受限句柄，随后需要已移除权限的操作才会失败。

Post 回调读取 `ReturnStatus`，操作成功时才读取 `Parameters` 中的授权结果，如 `GrantedAccess`。Post 信息只读，用于记录结果，权限裁剪应在 Pre 完成。

### 进程句柄裁剪示例

以下 `object.c` 片段只处理指定实验进程的用户句柄。跳过内核句柄是此示例的覆盖选择，实际策略需要单独定义该路径。

```c
OB_PREOP_CALLBACK_STATUS OnObjectPre(
    PVOID RegistrationContext,
    POB_PRE_OPERATION_INFORMATION Info
)
{
    if (Info->ObjectType != *PsProcessType || Info->KernelHandle ||
        !IsProtectedLabProcess((PEPROCESS)Info->Object)) {
        return OB_PREOP_SUCCESS;
    }

    ACCESS_MASK* access;
    if (Info->Operation == OB_OPERATION_HANDLE_CREATE) {
        access = &Info->Parameters->CreateHandleInformation.DesiredAccess;
    } else if (Info->Operation == OB_OPERATION_HANDLE_DUPLICATE) {
        access = &Info->Parameters->DuplicateHandleInformation.DesiredAccess;
    } else {
        return OB_PREOP_SUCCESS;
    }

    *access &= ~(PROCESS_TERMINATE | PROCESS_CREATE_THREAD |
                 PROCESS_VM_OPERATION | PROCESS_VM_WRITE);
    return OB_PREOP_SUCCESS;
}
```

## 与进程生命周期和已有授权的关系

| 场景 | 进程通知与句柄过滤的关系 |
|---|---|
| 创建新进程 | Ps 描述生命周期；同一业务流程中的进程、线程句柄建立可另由 Ob 描述。 |
| 打开已有进程 | Ob 处理新句柄申请；目标进程生命周期未因此重新开始。 |
| 复制已有句柄 | Ob 描述权限和句柄表间流转，目标对象保持不变。 |
| 使用已有句柄写内存 | 操作使用既有授权，不会每次都重新触发句柄创建或复制回调。 |

注册 Ob 回调或更新策略主要影响后续句柄操作，既有句柄权限不会因此被追溯修改。验证时应分别检查策略启用前后的句柄，并测试实际授权及后续操作，而不只观察 `OpenProcess` 的返回值。

# 注册表过滤

Configuration Manager 管理注册表，`CmRegisterCallbackEx` 从 Windows Vista 起提供带高度和驱动对象的回调注册。它直接接入注册表操作，与文件系统过滤器的注册相互独立。

## 回调注册与通知分类

注册时向 `CmRegisterCallbackEx` 提供回调、高度、驱动对象和可选自定义上下文，保存成功返回的 Cookie，用于名称查询等操作以及后续 `CmUnRegisterCallback`。

回调形式为 `NTSTATUS OnRegistryNotify(PVOID CallbackContext, PVOID Argument1, PVOID Argument2)`。`Argument1` 承载通知枚举值，`Argument2` 指向该类别的信息结构：

```c
REG_NOTIFY_CLASS kind = (REG_NOTIFY_CLASS)(ULONG_PTR)Argument1;
```

先判断 `kind`，再转换 `Argument2`。常见操作及其前后通知如下：

| 操作 | Pre / Post 通知 |
|---|---|
| 创建键 | `RegNtPreCreateKeyEx` / `RegNtPostCreateKeyEx` |
| 打开键 | `RegNtPreOpenKeyEx` / `RegNtPostOpenKeyEx` |
| 设置值 | `RegNtPreSetValueKey` / `RegNtPostSetValueKey` |
| 删除值 | `RegNtPreDeleteValueKey` / `RegNtPostDeleteValueKey` |
| 删除键 | `RegNtPreDeleteKey` / `RegNtPostDeleteKey` |
| 重命名键 | `RegNtPreRenameKey` / `RegNtPostRenameKey` |

## Pre、Post 与状态控制

Pre 返回 `STATUS_SUCCESS` 让操作继续；返回使 `NT_SUCCESS(status)` 为假的状态可拒绝操作。前置拒绝后不会收到对应 Post，因此拒绝日志和该路径的资源释放必须在 Pre 或自有清理路径完成。

Post 可以按接口规则修改输出参数并返回 `STATUS_SUCCESS`；需要改变调用方所见状态时，设置 `REG_POST_OPERATION_INFORMATION.ReturnStatus` 并返回 `STATUS_CALLBACK_BYPASS`。把成功改为失败时可能需要释放已经产生的对象，把失败改为成功时需要提供有效输出。

Pre 返回 `STATUS_CALLBACK_BYPASS` 表示过滤器已接管并完成操作，系统不再执行原操作，也不再发送对应 Post。此时驱动必须提供正确输出，不能仅用这个状态替代拒绝。[注册表通知处理与返回语义](https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/handling-notifications)

## 键名称、对象与上下文

注册表通知常提供键对象。`CmCallbackGetKeyObjectIDEx` 根据有效对象获取键标识和名称；使用后调用 `CmCallbackReleaseKeyObjectIDEx` 释放取得的名称。这组 Ex 接口从 Windows 8 起可用。

名称匹配应统一名称空间。例如内核名称 `\REGISTRY\MACHINE\SOFTWARE\EdrLab` 对应用户界面中的 `HKLM\SOFTWARE\EdrLab`，两者需要转换后比较。

`RegNtPostCreateKeyEx` 和 `RegNtPostOpenKeyEx` 中，只有 `REG_POST_OPERATION_INFORMATION.Status == STATUS_SUCCESS` 时 `Object` 才有效。其他状态即使满足 `NT_SUCCESS`，对象字段也可能未定义。键关闭、对象上下文清理等通知还可能携带正在销毁的键对象，应遵守该通知的访问规则，不能仅凭非空就增加引用。[注册表通知中的无效对象指针](https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/invalid-key-object-pointers-in-registry-notifications)

`CallContext` 关联一次操作的前后处理；`CmSetCallbackObjectContext` 将上下文关联到键对象，并通过对应清理通知管理释放。二者分别跟随操作与对象生命周期。

## 限制测试键的设置值操作

以下是 `registry.c` 的处理流程伪代码，只拒绝指定键的设置值操作：

```text
收到通知
  若类别不是 RegNtPreSetValueKey：返回 STATUS_SUCCESS
  按 REG_SET_VALUE_KEY_INFORMATION 读取 Object
  使用 Cookie 和 Object 调用 CmCallbackGetKeyObjectIDEx
  若名称查询失败：记录失败计数，返回 STATUS_SUCCESS
  比较键名与 \REGISTRY\MACHINE\SOFTWARE\EdrLab，忽略大小写
  在当前回调内复制需要上报的键名、值名及裁决
  调用 CmCallbackReleaseKeyObjectIDEx 释放名称
  命中时返回 STATUS_ACCESS_DENIED，否则返回 STATUS_SUCCESS
```

该路径选择名称解析失败时放行，即 fail-open。删除、重命名、创建子键等操作需要各自策略；名称失败、内存不足和采集失败也应分别定义处理方式，避免辅助函数的错误路径意外决定全局阻断行为。

通知中的缓冲区与嵌套指针应按对应结构和系统版本的规则访问；异步任务只能接收已安全复制或按规则持有的数据。回调中再次发起注册表操作还需控制重入。

# 文件系统过滤

Minifilter 通过 `FltMgr.sys` 管理与文件系统之间的交互。驱动登记参与的 I/O 类型，Filter Manager 负责过滤实例与请求流转；传统 Legacy Filter 则需要自行管理过滤附加链。

## Filter、Instance 与 Altitude

| 对象或属性 | 职责 |
|---|---|
| Filter | 表示已向 FltMgr 注册的过滤驱动。 |
| Instance | 表示该过滤驱动附加到某个卷上的实例。 |
| Altitude | 决定实例在文件过滤栈中的相对位置。 |

运行状态需要依次确认驱动加载、Filter 注册和目标卷的 Instance 附加。I/O 的 Pre 通常从较高实例向较低实例传递，Post 沿相反方向返回；此排序仅适用于文件过滤栈。

## 注册与启动

`FLT_OPERATION_REGISTRATION` 数组指定要参与的操作和 Pre/Post 函数，以 `IRP_MJ_OPERATION_END` 结束。`FLT_REGISTRATION` 描述过滤器，包含结构大小、版本、操作数组及 `FilterUnloadCallback` 等回调。

注册与启用具有明确先后关系：

```text
准备策略、锁、队列和停止状态
    ↓
配置 FLT_REGISTRATION 与操作数组
    ↓
FltRegisterFilter 成功，保存 PFLT_FILTER
    ↓
FltStartFiltering
    ├─ 成功：进入正常过滤生命周期
    └─ 失败：FltUnregisterFilter，清除登记状态并回滚
```

`FltStartFiltering` 返回前就可能收到回调，共享状态必须提前就绪。卸载回调应接入统一退出流程，完成实例、工作项与挂起请求的协调。[FltStartFiltering](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/fltkernel/nf-fltkernel-fltstartfiltering)

## I/O 类型与返回语义

| 操作类型 | 覆盖内容 |
|---|---|
| `IRP_MJ_CREATE` | 打开或创建文件、目录。 |
| `IRP_MJ_READ` / `IRP_MJ_WRITE` | 数据读取、写入。 |
| `IRP_MJ_SET_INFORMATION` | 重命名、删除处置和其他信息修改。 |
| `IRP_MJ_CLEANUP` / `IRP_MJ_CLOSE` | 句柄清理与对象关闭相关处理。 |

Minifilter 只参与自己注册的操作。只注册 Create 可以控制新的打开请求，读写、已有句柄、映射、缓存与分页路径的保护需要另行设计。

| Pre 返回值 | 后续处理 |
|---|---|
| `FLT_PREOP_SUCCESS_NO_CALLBACK` | 继续下发，不调用本过滤器的 Post。 |
| `FLT_PREOP_SUCCESS_WITH_CALLBACK` | 继续下发，完成时调用已注册的 Post。 |
| `FLT_PREOP_COMPLETE` | 由本过滤器完成，必须设置最终 `IoStatus`。 |
| `FLT_PREOP_PENDING` | 在受支持的 IRP 路径挂起，驱动承担后续完成责任。 |
| `FLT_PREOP_DISALLOW_FASTIO` | 拒绝当前 Fast I/O 路径，后续可能改走其他 I/O 路径。 |

返回 `FLT_PREOP_COMPLETE` 后，请求不再传给更低过滤器和文件系统，本过滤器的 Post 也不执行；更高层已参与的过滤器仍可收到 Post。完成时 `CompletionContext` 必须为空，最终状态不能是 `STATUS_PENDING`；Cleanup 和 Close 不能失败。[Minifilter Pre 回调](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/fltkernel/nc-fltkernel-pflt_pre_operation_callback)

## 文件打开与名称匹配

以下 `file.c` 片段用名称策略拒绝指定实验文件的新打开请求，前提是目标卷已附加实例且已注册 Create Pre：

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
        FLT_FILE_NAME_NORMALIZED | FLT_FILE_NAME_QUERY_DEFAULT,
        &nameInfo);

    if (!NT_SUCCESS(status)) {
        RecordNameQueryFailure(status);
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
```

`FltGetFileNameInformation` 的可用性受 I/O 类型、缓存和执行上下文限制。此例在查询失败时记录并放行，名称查询成功后释放名称信息，再根据已得到的裁决返回。

完整保护需要先明确策略针对路径、文件对象还是写入内容，再选择操作与身份识别方式。单次 Create 名称匹配不控制已有句柄上的写入；Post 中改变返回状态也不能自动撤销已经发生的文件系统副作用。

## 挂起请求与完成责任

返回 `FLT_PREOP_PENDING` 后，驱动必须在后续路径调用 `FltCompletePendedPreOperation`，让请求继续或结束。挂起只适用于接口支持的 IRP 路径。

挂起请求可能因正常裁决、超时、请求取消或卸载而结束。这些路径需要协调到唯一完成者，既防止重复完成，也保证每个请求最终完成。卸载期间应保留完成请求所依赖的工作能力，直到所有相关请求得到处理。

Post 收到 `FLTFL_POST_OPERATION_DRAINING` 时，应清理完成上下文并按框架规则退出，停止执行正常业务处理。

# 网络过滤

Windows Filtering Platform（WFP）在连接授权、流和数据包等阶段提供过滤。固定条件的允许、阻断可以直接配置 Filter；需要自定义分类或数据处理时，再由 Callout 驱动参与。[WFP 架构](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/windows-filtering-platform-architecture-overview)

## Layer、Sublayer、Filter 与 Callout

| 对象 | 职责与关系 |
|---|---|
| Layer | 标识网络处理阶段，决定可用字段、数据结构和动作。 |
| Sublayer | 组织过滤器，参与排序与策略仲裁。 |
| Filter | 指定 Layer、Sublayer、匹配条件和动作；动作可以引用 Callout。 |
| Callout | 提供自定义分类、通知及可选的流清理函数。 |

例如，应用发起出站连接，到达 `ALE_AUTH_CONNECT` 层后匹配 Filter 的应用条件；该 Filter 的动作引用某个 Callout，引擎才调用其 `classifyFn`。Callout 是被规则引用的独立对象，注册运行时函数本身不会让全部流量经过它。

## 管理面与运行时

`Fwps*` 提供内核运行时接口，例如 `FwpsCalloutRegister0` 和 `FwpsCalloutUnregisterById0`；`Fwpm*` 管理引擎对象，例如打开会话、添加 Sublayer、Callout 和 Filter。部分 `Fwpm*` 同时有内核版本；本文选择服务管理规则、驱动实现运行时 Callout。

函数与结构名称中的 `0`、`1`、`2` 是版本后缀。结构和回调签名需成套使用：`FWPS_CALLOUT0` 的 `classifyFn` 有六个参数，不包含后续版本中的额外 `classifyContext`。

## 过滤层与事件归因

| 过滤层 | 主要用途 |
|---|---|
| `ALE_AUTH_CONNECT_V4/V6` | 出站连接授权，常用于按应用控制新连接。 |
| `ALE_AUTH_RECV_ACCEPT_V4/V6` | 入站接收、连接接受授权。 |
| `ALE_FLOW_ESTABLISHED_V4/V6` | 已建立流的关联与跟踪。 |
| `STREAM_V4/V6` | TCP 数据流处理。 |
| `DATAGRAM_DATA_V4/V6` | 数据报处理，常用于 UDP。 |
| Transport / IP Packet 相关层 | 传输层或 IP 数据包处理。 |

层决定 `layerData` 类型、可用字段及元数据。读取进程 ID 前，应检查 `currentMetadataValues & FWPS_METADATA_FIELD_PROCESS_ID`；归因依据有效元数据，不能把当前分类线程所属进程统一视为连接发起者。

## 运行时 Callout 注册与裁决

驱动先创建设备对象，再构造 `FWPS_CALLOUT0`：设置 `calloutKey`、`classifyFn`、`notifyFn`，按是否关联流上下文配置 `flowDeleteFn`。`FwpsCalloutRegister0` 成功后返回运行时 ID，必须保存以供注销。

以下 `network.c` 片段用于实验阻断规则：只有命中引用它的 Filter 且有动作写权限时，才执行阻断。

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
}
```

`FWP_ACTION_CONTINUE` 把裁决交给后续过滤器，最终结果仍受仲裁影响。上例遇到无写权限时直接返回；WFP 另有对已有 Permit 执行 Veto 的规则，该示例未采用此路径。[分类输出与动作权限](https://learn.microsoft.com/en-us/windows/win32/api/fwpstypes/ns-fwpstypes-fwps_classify_out0)

## 管理对象与匹配规则

示例服务在运行时 Callout 注册成功后，用动态会话配置指定实验程序的 IPv4 出站授权规则：

```text
FwpmEngineOpen0（FWPM_SESSION_FLAG_DYNAMIC）
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

核心配置关系如下，GUID 均为项目自行定义的标识：

| 配置位置 | 示例取值或约束 |
|---|---|
| 运行时与管理面 `calloutKey` | 使用同一个 Callout GUID。 |
| 管理面 Callout 的 `applicableLayer` | `FWPM_LAYER_ALE_AUTH_CONNECT_V4`。 |
| Filter 的 `layerKey` | 与 Callout 的适用层一致。 |
| Filter 的 `subLayerKey` | 引用已添加的实验 Sublayer。 |
| Filter 条件 | `FWPM_CONDITION_ALE_APP_ID`，使用 `FWP_MATCH_EQUAL` 与应用标识匹配。 |
| 条件值 | `FWP_BYTE_BLOB_TYPE`，指向为实验程序取得的 WFP 应用标识。 |
| Filter 动作 | `FWP_ACTION_CALLOUT_TERMINATING`，引用同一 Callout GUID。 |

子层和过滤器权重应按策略仲裁需求配置。此规则只针对指定程序的 IPv4 新连接授权；IPv6 需要对应层与规则。

用户态 `Fwpm*` 返回 `DWORD` 错误码，应与 `ERROR_SUCCESS` 比较。事务开始失败时直接结束；事务内添加失败时显式调用 `FwpmTransactionAbort0`，提交失败也要进入错误清理。各对象成功创建与事务成功提交应分别记录。

## 会话、网络流与撤销

动态会话结束时，其管理对象自动删除，因此策略有效期间服务需要保持引擎会话。会话结束只处理管理面对象，运行时 Callout 仍需显式注销。

撤销时先移除引用 Callout 的 Filter，再处理管理面 Callout、Sublayer 等依赖对象，随后注销运行时 Callout，最后释放设备和自有资源。若先注销运行时 Callout，遗留终止型 Filter 可能按阻断处理，使网络仍受影响。

关联的流上下文尚未移除时，`FwpsCalloutUnregisterById0` 可返回 `STATUS_DEVICE_BUSY`。驱动必须为相关流移除上下文并再次注销，直到所有 Callout 成功注销后才能卸载。[Callout 注销状态与遗留 Filter 的行为](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/fwpsk/nf-fwpsk-fwpscalloutunregisterbyid0)

新连接授权、已有连接处置和 TCP 流检查具有不同生命周期。授权层规则可以拒绝新的连接尝试，已有连接是否受影响需要按所选层、重新授权及流处理机制单独设计和验证。

# 其他内核通知

以下机制辅助产品生命周期管理，各自服务于所属子系统：

| 接口 | 关注范围 | 退出方式或条件 |
|---|---|---|
| `ExRegisterCallback` | 在回调对象上登记通知 | `ExUnregisterCallback`。 |
| `IoRegisterPlugPlayNotification` | 即插即用事件 | `IoUnregisterPlugPlayNotificationEx` 等对应接口。 |
| `IoRegisterFsRegistrationChange` | 文件系统注册状态变化，常用于传统过滤场景 | `IoUnregisterFsRegistrationChange`；事件对象为注册状态。 |
| `PoRegisterPowerSettingCallback` | 电源设置变化 | `PoUnregisterPowerSettingCallback`。 |
| `SeRegisterLogonSessionTerminatedRoutine` | 登录会话终止 | 关联的最后一个令牌引用消失后才满足终止条件。 |
| `IoRegisterShutdownNotification` | 为设备登记关机处理 | 设备接收 `IRP_MJ_SHUTDOWN`。 |
| `KeRegisterBugCheckReasonCallback` | 系统崩溃期间的有限处理 | `KeDeregisterBugCheckReasonCallback`；执行环境受严格限制。 |

# 回调执行与驱动生命周期

## IRQL 与执行上下文

IRQL 描述内核执行约束，与普通线程优先级不同。检查接口时，要分别核对注册函数的调用条件和回调执行条件；即使回调运行在 `PASSIVE_LEVEL`，临界区、APC、锁和重入约束仍可能限制等待与通信。

| 回调 | 主要执行约束 |
|---|---|
| 进程 Ex 通知 | `PASSIVE_LEVEL`，临界区内，普通内核 APC 被禁用。 |
| 普通线程通知 | 可能为 `PASSIVE_LEVEL` 或 `APC_LEVEL`。 |
| 镜像加载通知 | `PASSIVE_LEVEL`，还受临界区和 APC 约束。 |
| Ob Pre / Post | `PASSIVE_LEVEL`，普通内核 APC 被禁用。 |
| 注册表回调 | 不高于 `APC_LEVEL`，遵守数据有效性与重入规则。 |
| Minifilter Pre | 可能为 `PASSIVE_LEVEL` 或 `APC_LEVEL`，上下文随 I/O 路径变化。 |
| Minifilter Post | 可能达到 `DISPATCH_LEVEL`。 |
| WFP `classifyFn` | 可能达到 `DISPATCH_LEVEL`，按层和数据类型处理。 |

这些条件决定可用内存、锁和 API。文件 Pre 可能在上层过滤器的工作线程中执行，线程所属进程与最初请求者可能不同；事件归因应使用框架提供的请求语义。

## 同步裁决与异步上报

同步路径在回调内读取本地策略快照，给出该节点允许的处理结果并及时返回。异步路径复制必要字段，送入有界队列，由工作线程或服务消费。

Ps 或 Ob 回调返回后，服务稍后的分析结果不能补写为该次操作的同步裁决。支持挂起的框架必须按自身协议保留请求，并承担超时、取消和卸载完成责任。

队列保存自有数据。长期保存对象时需遵守对象引用和框架规则；借用指针不能直接跨越回调有效期。事件协议至少应表达事件类别、时间和本地序号、执行上下文、目标资源、原始请求、本地裁决、策略版本，以及字段缺失或采集失败状态。

字段不存在、查询失败与值为空应分别编码；队列满时执行明确的丢弃或降级策略并计数，防止采集压力变成无界内存增长或同步等待。

## 初始化与失败回滚

初始化先准备策略、锁、队列和停止状态，再按依赖关系注册模块，最后开放正常控制与消费路径。每个模块保存自己的注册状态和资源标识。

例如 Ps、Ob 注册成功而 Cm 失败时，只撤销已经成功建立的资源，并等待相关活动退出。文件过滤启用后可能立即回调，WFP 又具有管理对象与运行时对象间的依赖，这些条件必须体现在模块初始化和失败回滚中。

## 注册与注销配对

| 注册入口 | 注销方式 | 保存内容 |
|---|---|---|
| `PsSetCreateProcessNotifyRoutine` / Ex / Ex2 | 对应接口传 `Remove = TRUE` | 原回调；Ex2 还需匹配通知类型。 |
| `PsSetCreateThreadNotifyRoutine` / Ex | `PsRemoveCreateThreadNotifyRoutine` | 原回调。 |
| `PsSetLoadImageNotifyRoutine` / Ex | `PsRemoveLoadImageNotifyRoutine` | 原回调。 |
| `ObRegisterCallbacks` | `ObUnRegisterCallbacks` | 注册句柄。 |
| `CmRegisterCallbackEx` | `CmUnRegisterCallback` | Cookie。 |
| `FltRegisterFilter` | `FltUnregisterFilter` | `PFLT_FILTER`。 |
| `FwpsCalloutRegister0` | `FwpsCalloutUnregisterById0` 或对应 Key 接口 | 运行时 ID 或 Key。 |

进程 Ex 注销会等待正在执行的回调结束，必须从自身回调之外发起；注册表回调也不能在自身回调中调用注销，否则可能死锁。各模块应按具体 API 的等待契约安排退出线程。

## 卸载与资源排空

完整退出过程包括进入停止状态、拒绝新控制请求和新自有任务、停止事件来源、处理挂起操作、等待回调及工作项、释放引用与通信资源，最后完成卸载。

停止来源与完成挂起操作的先后关系应服从框架依赖。例如，Minifilter 的待完成请求仍依赖工作线程时，应先保留该线程完成请求；WFP 注销返回忙状态时，应先解决关联流上下文。

框架注销完成后，自建事件队列可能仍有待消费数据，必须单独排空或按既定策略释放。多模块驱动还应把 Minifilter 的卸载回调接入统一清理，防止过滤器路径与普通驱动退出路径重复释放或互相遗漏。

## 用户态通信

驱动可以通过设备控制接口与服务通信，Minifilter 也提供通信端口。协议需要校验调用权限、长度和状态，限制可访问对象与操作范围。通用内核地址读写或任意函数调用不应成为监控接口的一部分。

服务断开、重启或策略更新失败时，驱动应按预设的本地策略继续、降级或拒绝相应操作，并记录状态，避免无限期等待用户态响应。

# 运行与验证

## 实验使用路径

实际验证需要补齐工程、签名、安装配置、事件消费和测试程序。可用 `LabTarget.exe` 作为目标进程，`LabCaller.exe` 申请和复制句柄，`LabClient.exe` 发起网络连接；注册表使用 `\REGISTRY\MACHINE\SOFTWARE\EdrLab`，文件使用独立实验目录中的指定对象。

先在仅采集模式建立基线，再逐项启用阻断规则，并检查调用方结果、内核裁决和事件记录是否一致。下面列出设计输入与预期断言，未表示已经执行这些测试。

| 输入 | 预期验证点 |
|---|---|
| 正常启动、退出目标进程 | 创建、退出可关联，父进程与实际创建者分别保存。 |
| 创建目标中的线程并加载镜像 | 线程与镜像字段按各自语义解析，缺失名称和系统镜像单独处理。 |
| 启用进程拒绝规则后启动目标 | `CreationStatus` 导致创建被否决，事件保存本地裁决。 |
| 打开已运行的目标 | 产生句柄授权事件，目标生命周期保持原有关系。 |
| 跨进程复制目标句柄 | 正确识别源句柄表、目标句柄表与被引用对象。 |
| 取得裁剪后的句柄 | 检查实际权限；依赖移除权限的操作失败，即使取得句柄成功。 |
| 使用策略启用前的句柄 | 单独验证既有授权，明确新策略覆盖边界。 |
| 设置受保护键的值 | Pre 拒绝后值未被该操作修改，拒绝记录不依赖 Post。 |
| 打开实验文件 | 实例已附加、名称查询成功并匹配时，Create 被拒绝。 |
| 实验客户端发起新 IPv4 连接 | 命中目标 Filter 与 Callout；IPv6、已有连接另测。 |
| 撤销动态网络策略 | 管理对象被移除，网络状态符合撤销预期，无遗留规则影响。 |

## 检查过滤实例与网络规则

在已部署实验驱动的管理员终端中，可检查文件过滤器、实例和卷：

```powershell
fltmc filters
fltmc instances
fltmc volumes
```

`filters` 确认 Filter，`instances` 确认目标卷附加；过滤器已列出但目标卷缺少实例时，先定位附加与配置。

WFP 当前状态可导出为文件：

```powershell
netsh wfp show state file=wfpstate.xml
```

检查 Filter 的 Layer、Sublayer、Callout Key 与应用条件，同时核对运行时注册结果。管理规则匹配正确与运行时函数已注册是两个独立条件。

## 覆盖缺口定位

| 检查环节 | 核对内容 |
|---|---|
| 注册 | 返回状态、重复注册、资源标识是否保存。 |
| 附加和规则 | Minifilter 目标卷实例、WFP 层与匹配条件。 |
| 事件语义 | 行为是否属于已注册的操作类型。 |
| 生命周期 | 行为发生时间、是否使用旧句柄或已有连接。 |
| 采集 | 查询、复制和内存分配的失败计数。 |
| 上报 | 队列上限、丢弃统计、服务连接状态。 |
| 策略 | 对象身份、名称空间和策略版本。 |

缺少日志可能发生在任何一个环节，应沿事件路径定位。驱动已加载也只证明其中一个前提成立；内核保护、代码完整性和已签名驱动仍有各自边界，单一回调无法独立覆盖所有防护目标。

## 并发、异常与卸载

| 场景 | 重点断言 |
|---|---|
| 大量进程、线程和句柄并发操作 | 无竞态、长期锁竞争和不可控内存增长。 |
| 队列达到上限 | 丢弃或降级策略明确，有计数且无无限等待。 |
| 用户态服务退出、重启 | 内核行为符合失败策略，通信状态可恢复。 |
| 任一模块注册失败 | 成功部分完整回滚，无残留回调或过滤对象。 |
| 文件请求挂起期间卸载 | 请求得到完成或取消，每个请求只完成一次。 |
| 仍有网络流上下文时注销 | 处理忙状态后成功注销，再释放驱动。 |
| 反复加载、卸载和切换策略 | 无重复注册、泄漏、悬空指针及旧策略残留。 |

在可恢复测试虚拟机中，可只对实验驱动配置 Driver Verifier：

```powershell
verifier /standard /driver EdrLab.sys
```

按要求重启后运行测试，查看配置：

```powershell
verifier /querysettings
```

实验结束后清除配置并重启使其生效：

```powershell
verifier /reset
```

Verifier 用于暴露驱动违规；发生蓝屏时，结合转储定位出错路径，并重新验证对应的并发、资源和退出条件。
