export default {
  reviewList: {
    title: '用例评审',
    createReview: '新建评审',
    project: '项目',
    selectProject: '请选择项目',
    status: '评审状态',
    selectStatus: '请选择状态',
    reviewer: '评审人',
    selectReviewer: '请选择评审人',
    search: '搜索',
    reset: '重置',

    // Table columns
    reviewTitle: '评审标题',
    reviewProject: '项目',
    reviewStatus: '评审状态',
    priority: '优先级',
    creator: '创建人',
    testcaseCount: '用例数量',
    progress: '评审进度',
    deadline: '截止时间',
    createdAt: '创建时间',
    actions: '操作',

    // Status
    statusPending: '待评审',
    statusInProgress: '评审中',
    statusApproved: '已通过',
    statusRejected: '未通过',
    statusCancelled: '已取消',

    // Priority
    priorityLow: '低',
    priorityMedium: '中',
    priorityHigh: '高',
    priorityCritical: '紧急',

    // Actions
    execute: '开始评审',
    detail: '详情',
    review: '评审',
    edit: '编辑',
    delete: '删除',

    // Review dialog
    submitReview: '提交评审',
    reviewResult: '评审结果',
    approved: '通过',
    rejected: '未通过',
    reviewComment: '评审意见',
    reviewCommentPlaceholder: '请输入评审意见',
    submit: '提交',
    cancel: '取消',

    // Messages
    deleteConfirm: '确定要删除这条评审吗？',
    deleteSuccess: '删除成功',
    deleteFailed: '删除失败',
    submitSuccess: '提交成功',
    submitFailed: '提交失败',
    fetchListFailed: '获取评审列表失败',
    fetchProjectsFailed: '获取项目列表失败',
    fetchReviewersFailed: '获取评审人列表失败',

    // Empty state
    noData: '暂无数据',
    noDeadline: '无截止时间'
  },

  // Review Detail Page
  reviewDetail: {
    title: '评审详情',
    back: '返回',
    edit: '编辑',
    submitReview: '提交评审',

    // Basic Info Card
    basicInfo: '基本信息',
    reviewTitle: '评审标题',
    associatedProject: '关联项目',
    notSet: '未设置',
    creator: '创建人',
    useTemplate: '使用模板',
    noTemplate: '未使用模板',
    reviewStatus: '评审状态',
    priority: '优先级',
    deadline: '截止时间',
    none: '无',
    createdAt: '创建时间',
    reviewDescription: '评审描述',

    // Progress Card
    reviewProgress: '评审进度',
    reviewers: '评审人员',
    completed: '已完成',
    pendingReview: '待评审',

    // Reviewers Card
    reviewersCard: '评审人员',
    reviewer: '评审人',
    reviewerStatus: '评审状态',
    reviewerComment: '评审意见',
    checklist: '检查清单',
    notFilled: '未填写',
    assignedAt: '分配时间',
    reviewedAt: '评审时间',
    pendingReviewTime: '待评审',

    // Assignment Status
    assignmentPending: '待评审',
    assignmentApproved: '已通过',
    assignmentRejected: '已拒绝',
    assignmentAbstained: '弃权',

    // Testcases Card
    reviewTestcases: '评审用例',
    testcaseTitle: '用例标题',
    testType: '测试类型',
    author: '作者',
    view: '查看',
    comment: '评论',

    // Test Types
    testTypeFunctional: '功能测试',
    testTypeIntegration: '集成测试',
    testTypeApi: 'API测试',
    testTypeUi: 'UI测试',
    testTypePerformance: '性能测试',
    testTypeSecurity: '安全测试',

    // Comments Card
    reviewComments: '评审意见',
    addComment: '添加意见',
    relatedTestcase: '相关用例',
    noComments: '暂无评审意见',

    // Comment Types
    commentTypeGeneral: '整体意见',
    commentTypeTestcase: '用例意见',
    commentTypeStep: '步骤意见',

    // Submit Review Dialog
    submitReviewDialog: '提交评审',
    reviewResult: '评审结果',
    approved: '通过',
    rejected: '拒绝',
    abstained: '弃权',
    checklistTitle: '检查清单',
    allPass: '全部通过',
    allFail: '全部不通过',
    reviewCommentLabel: '评审意见',
    reviewCommentPlaceholder: '请输入评审意见',
    cancel: '取消',
    submit: '提交',

    // Add Comment Dialog
    addCommentDialog: '添加评审意见',
    commentType: '意见类型',
    generalComment: '整体意见',
    testcaseComment: '用例意见',
    relatedTestcaseLabel: '相关用例',
    selectTestcase: '请选择用例',
    commentContent: '意见内容',
    commentContentPlaceholder: '请输入意见内容',

    // Checklist Stats
    checklistPass: '通过',
    checklistFail: '不通过',
    checklistTotal: '总计',

    // Messages
    fetchDetailFailed: '获取评审详情失败',
    submitSuccess: '评审提交成功',
    submitFailed: '评审提交失败',
    addCommentSuccess: '意见添加成功',
    addCommentFailed: '意见添加失败',
    commentRequired: '请输入意见内容'
  },

  // Review Form Page
  reviewForm: {
    createTitle: '新建评审',
    editTitle: '编辑评审',
    back: '返回',
    save: '保存',

    // Form Fields
    reviewTitle: '评审标题',
    reviewTitlePlaceholder: '请输入评审标题',
    associatedProject: '关联项目',
    selectProject: '请选择项目',
    priority: '优先级',
    selectPriority: '请选择优先级',
    priorityLow: '低',
    priorityMedium: '中',
    priorityHigh: '高',
    priorityUrgent: '紧急',
    deadline: '截止日期',
    deadlinePlaceholder: '请选择截止日期',
    description: '评审描述',
    descriptionPlaceholder: '请输入评审描述',

    // Testcase Selection
    selectTestcases: '选择用例',
    searchTestcases: '搜索用例',
    selectTestcasesBtn: '选择用例',
    emptyTestcasesTip: '请选择要评审的测试用例',

    // Reviewers
    reviewers: '评审人员',
    selectReviewers: '请选择评审人员',

    // Template
    reviewTemplate: '评审模板',
    selectTemplate: '可选择评审模板',

    // Testcase Selector
    testcaseSelectorTitle: '选择测试用例',
    selectVersion: '选择迭代',
    selectVersionPlaceholder: '请选择迭代（可选）',
    selectModules: '选择模块',
    selectModulesPlaceholder: '请选择模块（可多选）',
    totalCases: '总计用例',
    cases: '个用例',
    emptyTestcasesTip: '请选择模块以包含其所有用例',

    // Validation
    titleRequired: '请输入评审标题',
    projectRequired: '请选择项目',
    testcasesRequired: '请选择要评审的用例',
    reviewersRequired: '请选择评审人员',
    selectProjectFirst: '请先选择项目',

    // Messages
    createSuccess: '评审创建成功',
    updateSuccess: '评审更新成功',
    saveFailed: '保存失败',
    fetchProjectsFailed: '获取项目列表失败',
    fetchUsersFailed: '获取用户列表失败',
    fetchTestcasesFailed: '获取用例列表失败',
    fetchTemplatesFailed: '获取模板列表失败',
    fetchReviewFailed: '获取评审数据失败'
  },
  reviewTemplate: {
    title: '评审模板',
    createTemplate: '创建模板',
    useTemplate: '使用',
    edit: '编辑',
    delete: '删除',

    // Filter
    project: '项目',
    selectProject: '请选择项目',

    // Card labels
    projectLabel: '项目:',
    creatorLabel: '创建人:',
    createdAtLabel: '创建时间:',
    descriptionLabel: '描述',
    checklistTitle: '检查清单:',
    reviewersTitle: '默认评审人:',

    // Empty states
    noDescription: '暂无描述',
    noChecklist: '暂无检查清单',
    noReviewers: '未设置默认评审人',
    noData: '暂无评审模板',
    moreItems: '还有 {count} 项...',

    // Dialog
    createTitle: '创建模板',
    editTitle: '编辑模板',
    templateName: '模板名称',
    templateNamePlaceholder: '请输入模板名称',
    associatedProject: '关联项目',
    templateDescription: '模板描述',
    templateDescriptionPlaceholder: '请输入模板描述',
    checklist: '检查清单',
    checklistItemPlaceholder: '请输入检查项',
    addChecklistItem: '添加检查项',
    defaultReviewers: '默认评审人',
    selectDefaultReviewers: '请选择默认评审人',
    save: '保存',
    cancel: '取消',

    // Validation
    nameRequired: '请输入模板名称',
    projectRequired: '请选择项目',

    // Messages
    deleteConfirm: '确定要删除这个模板吗？',
    deleteSuccess: '删除成功',
    deleteFailed: '删除失败',
    createSuccess: '模板创建成功',
    createFailed: '模板创建失败',
    updateSuccess: '模板更新成功',
    updateFailed: '模板更新失败',
    fetchListFailed: '获取模板列表失败',
    fetchProjectsFailed: '获取项目列表失败',
    fetchUsersFailed: '获取用户列表失败'
  },

  // 评审执行页面
  reviewExecution: {
    title: '评审执行',
    back: '返回',
    noProject: '无关联项目',

    // 统计
    total: '总用例数',
    passed: '通过',
    failedStatus: '不通过',
    unreviewed: '未评审',
    progress: '评审进度',

    // 表格
    serialNumber: '序号',
    caseTitle: '用例标题',
    status: '评审状态',
    comments: '评审备注',
    reviewedBy: '评审人',
    reviewedAt: '评审时间',
    actions: '操作',

    // 操作按钮
    viewHistory: '评审历史',
    editCase: '修改用例',
    addComment: '评审备注',

    // 状态
    statusUpdateSuccess: '评审状态更新成功',
    statusUpdateFailed: '评审状态更新失败',

    // 备注
    commentsUpdateSuccess: '评审备注更新成功',
    commentsUpdateFailed: '评审备注更新失败',
    commentsPlaceholder: '请输入评审备注',

    // 修改用例
    editCaseTitle: '修改用例数据',
    caseUpdateSuccess: '用例数据更新成功',
    caseUpdateFailed: '用例数据更新失败',

    // 历史
    reviewHistory: '评审历史',
    fetchHistoryFailed: '获取评审历史失败',

    // 筛选
    filterByModule: '模块筛选',
    allModules: '全部模块',

    // 批量操作
    batchDelete: '批量删除',
    batchUpdateStatus: '批量状态',
    batchSetPassed: '批量通过',
    batchSetFailed: '批量不通过',
    batchSetUnreviewed: '批量重置未评审',
    batchSelected: '已选',
    batchStatusConfirm: '确定将选中的 {count} 条用例状态改为 "{status}" 吗？',
    batchStatusSuccess: '成功更新 {count} 条用例状态为 "{status}"',
    batchStatusFailed: '批量状态更新失败',
    batchDeleteConfirm: '确定要删除选中的 {count} 条评审用例吗？',
    batchDeleteSuccess: '成功删除 {successCount} 条，失败 {failCount} 条',
    batchDeleteFailed: '批量删除失败',
    selectCasesFirst: '请先选择要删除的用例',

    // 消息
    fetchFailed: '获取评审信息失败',
    fetchCasesFailed: '获取评审用例列表失败'
  }
}
