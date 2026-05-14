// Client-side i18n. Default language is English; Chinese is opt-in via the
// nav-bar toggle. Templates carry English text inline so the page renders fine
// even before this script loads. Elements with `data-i18n="key"` get replaced
// at DOMContentLoaded; same for `data-i18n-attr="placeholder:key;title:key2"`.

const I18N_DICT = {
  en: {
    // App-wide
    'app.title': '📚 LeetCode Trainer',
    'nav.today': "Today's Review",
    'nav.add': 'Add Problem',
    'nav.list': 'Problem List',
    'nav.calendar': 'Calendar',
    'nav.english': 'English',
    'nav.settings': 'Settings',
    'nav.logout': 'Sign out',
    'theme.toggle': 'Toggle theme',

    // Common
    'common.save': 'Save',
    'common.delete': 'Delete',
    'common.cancel': 'Cancel',
    'common.edit': 'Edit',
    'common.loading': 'Loading…',
    'common.empty': 'Nothing here yet.',
    'common.confirm': 'Confirm',

    // Difficulty
    'diff.easy': 'Easy',
    'diff.medium': 'Medium',
    'diff.hard': 'Hard',

    // Mark / review status
    'mark.remembered': 'Got it ✅',
    'mark.fuzzy': 'Fuzzy 🤔',
    'mark.forgot': 'Forgot ❌',

    // Login & Register
    'login.title': '📚 LeetCode Trainer',
    'login.subtitle': 'Sign in to continue',
    'login.email': 'Email',
    'login.password': 'Password',
    'login.submit': 'Sign in',
    'login.noAccount': "Don't have an account?",
    'login.register': 'Sign up',
    'login.errBadCreds': 'Wrong email or password.',
    'register.title': '📚 Create your account',
    'register.subtitle': 'Start tracking your LeetCode review',
    'register.confirm': 'Confirm password',
    'register.submit': 'Create account',
    'register.pwHint': 'At least 6 characters.',
    'register.haveAccount': 'Already have an account?',
    'register.signIn': 'Sign in',
    'register.mismatch': "Passwords don't match",
    'register.errEmail': 'Invalid email address.',
    'register.errShort': 'Password must be at least 6 characters.',
    'register.errTaken': 'That email is already registered.',

    // Today page
    'today.title': "Today's Review",
    'today.statsLoading': 'Loading…',
    'today.stats': '{due} cards due, {done} reviewed today',
    'today.empty': "🎉 No cards due today. Go ",
    'today.emptyAddLink': 'add a new problem',
    'today.emptyOrRest': ' or take a break.',
    'today.needsGen': 'No cards yet →',
    'today.dueCards': '{n} concepts to review →',

    // Add page
    'add.title': 'Add Problem',
    'add.editTitle': 'Editing problem #{n}',
    'add.lcNumber': 'Problem # *',
    'add.titleField': 'Title',
    'add.titleHint': 'Auto-filled from LeetCode after you enter the problem number.',
    'add.titlePlaceholder': '(filled automatically after problem # is entered)',
    'add.difficulty': 'Difficulty',
    'add.tags': 'Tags',
    'add.tagsEmpty': '(no tags)',
    'add.tagsPlaceholder': '(filled automatically after problem # is entered)',
    'add.lookupBtn': 'Re-fetch metadata from LeetCode',

    'add.q1.label': '① Is your approach to this problem clear?',
    'add.q1.yes': 'Yes',
    'add.q1.no': 'No',
    'add.q1.hint': 'If "No", you must describe the approach below; the AI will always include a "describe the approach" question.',
    'add.q1.placeholder': "Describe the core approach in your own words: key idea, steps, why it works…\n(No need to copy the problem statement, the AI knows it.)",

    'add.q2.label': '② Syntax errors / language pitfalls',
    'add.q2.hint': 'Python syntax mistakes you made on this problem, or syntax patterns you weren\'t comfortable with (one per line).',
    'add.q2.placeholder': 'Examples:\n- collections.Counter.most_common() returns a list of tuples\n- Use \'\'.join(sorted(s)), not sorted(s).join(\'\')\n- defaultdict(list) cannot be initialized with a dict literal',

    'add.q3.label': '③ Style / optimization',
    'add.q3.hint': "Patterns that aren't wrong but could be better (space, readability, idiomatic Python, etc.).",
    'add.q3.placeholder': 'Examples:\n- The cur_max[i] array is redundant; a single var cur_max suffices, O(n)→O(1)\n- range(1, n) plus special-casing nums[0] can be simplified to range(0, n) with init 0',

    'add.q4.label': '④ Other notes (optional, Markdown supported)',
    'add.q4.hint': "Anything that doesn't fit above: problem statement, follow-ups, interview takeaways…",
    'add.q4.placeholder': '## Problem statement\n...\n\n## Follow-up\n...',

    'add.q5.label': '⑤ Private notes',
    'add.q5.badge': 'never sent to AI',
    'add.q5.hint': "For things you want to remember but don't want quizzed on — e.g. how to explain this problem in English, personal context, soft notes.",
    'add.q5.placeholder': "Examples:\n- English phrasing: 'Group strings that are anagrams using sorted-string as canonical key'\n- Felt nervous on this one in mock interview, want to redo",

    'add.btnSave': 'Save',
    'add.btnGoReview': 'Go to review →',
    'add.btnDelete': 'Delete',

    'add.toast.added': 'Added — head to the review page to generate cards',
    'add.toast.saved': 'Saved',
    'add.toast.deleted': 'Deleted',
    'add.toast.titleRequired': 'Problem # and title are required',
    'add.toast.metaRequired': 'Enter a problem number first to auto-fill metadata',
    'add.toast.descRequired': 'You marked the approach as unclear — please describe it',
    'add.toast.fillNumberFirst': 'Enter a problem number first',
    'add.toast.editLockedMeta': 'Cannot change metadata in edit mode',
    'add.toast.lookupOk': 'Auto-filled LC {n}: {title}',
    'add.toast.deleteConfirm': 'Delete this problem? Its cards and review history will be wiped too.',

    // List page
    'list.title': 'Problem List',
    'list.count': '{n} problems',
    'list.filter.allDiff': 'All difficulties',
    'list.filter.tagPlaceholder': 'Filter by tag',
    'list.sort.lcNumber': 'Number',
    'list.sort.firstSolved': 'First solved',
    'list.sort.nextReview': 'Next review',
    'list.sort.reviewCount': 'Reviews',
    'list.sort.difficulty': 'Difficulty',
    'list.sort.updated': 'Last updated',
    'list.sort.asc': 'Asc ↑',
    'list.sort.desc': 'Desc ↓',
    'list.col.num': '#',
    'list.col.title': 'Title',
    'list.col.diff': 'Difficulty',
    'list.col.tags': 'Tags',
    'list.col.reviews': 'Reviews',
    'list.col.next': 'Next review',
    'list.col.actions': 'Actions',
    'list.action.review': 'Review',
    'list.action.edit': 'Edit',
    'list.empty': 'No problems yet. Go ',
    'list.emptyAddLink': 'add the first one',
    'list.emptyTail': '.',

    // Review page
    'review.editNotes': 'Edit notes',
    'review.cards.title': '🎯 Concept Quiz',
    'review.cards.stats': '{total} cards · {due} due',
    'review.cards.genFirst': '🤖 Generate cards with AI',
    'review.cards.genMore': '🤖 Generate more',
    'review.cards.empty': 'No cards yet. Click the AI button above to have the model generate questions from your notes.',
    'review.cards.allCaughtUp': '✨ No cards due right now, come back later.',
    'review.cards.futureToggle': '▸ Cards not yet due ({n})',
    'review.cards.futureToggleOpen': '▾ Cards not yet due ({n})',
    'review.cards.reviewedTimes': 'Reviewed {n}× · next: {date}',
    'review.cards.approachFirst': '🔒 Describe your approach first — other cards are hidden until you answer this one.',
    'review.cards.showHint': '💡 Hint',
    'review.cards.showAnswer': 'Show answer',
    'review.cards.editBtn': 'Edit',
    'review.cards.deleteBtn': 'Delete',

    'review.notes.title': '📝 Study notes',
    'review.notes.empty': 'No notes yet. Go ',
    'review.notes.editLink': 'edit page',
    'review.notes.q1Clear': '① Approach',
    'review.notes.q1Unclear': '① Approach (marked as unclear)',
    'review.notes.q1Mastered': '✓ Mastered',
    'review.notes.q1NotFilled': '(not filled)',
    'review.notes.q2': '② Syntax errors / language pitfalls',
    'review.notes.q3': '③ Style / optimization',
    'review.notes.q4': '④ Other notes',
    'review.notes.q5': '⑤ Private notes',
    'review.notes.q5Badge': 'AI-private',

    'review.toast.recorded': 'Recorded',
    'review.toast.generated': 'Generated {n} cards',
    'review.toast.cardSaved': 'Card saved',
    'review.toast.cardDeleted': 'Card deleted',
    'review.prompt.editQuestion': 'Question:',
    'review.prompt.editHint': 'Hint (leave blank if none):',
    'review.prompt.editAnswer': 'Reference answer (Markdown supported):',
    'review.prompt.deleteCard': 'Delete this card?\n\nQuestion: {q}',
    'review.btn.generating': 'Generating…',

    // Calendar page
    'calendar.title': 'Review Calendar',
    'calendar.todayBtn': 'Today',
    'calendar.dayHeader.mon': 'Mon',
    'calendar.dayHeader.tue': 'Tue',
    'calendar.dayHeader.wed': 'Wed',
    'calendar.dayHeader.thu': 'Thu',
    'calendar.dayHeader.fri': 'Fri',
    'calendar.dayHeader.sat': 'Sat',
    'calendar.dayHeader.sun': 'Sun',
    'calendar.cellCardCount': '{n} cards',
    'calendar.dayTitle': '{date} ({problems} problems · {cards} cards)',
    'calendar.dayCards': '{n} cards',
    'calendar.dayEmpty': 'Nothing scheduled this day.',
    'calendar.month': '{year} / {month}',

    // Settings page
    'settings.title': 'Settings',
    'settings.intervals.title': '📐 Review intervals (days, comma-separated)',
    'settings.intervals.hint': 'Each "Got it" advances one step; "Forgot" resets to step 0. Actual gap is multiplied by an ease factor.',
    'settings.intervals.save': 'Save',
    'settings.intervals.saved': 'Saved',
    'settings.intervals.invalid': 'Enter at least one non-negative integer',

    'settings.provider.title': '🤖 AI provider',
    'settings.provider.body1': 'Currently using: ',
    'settings.provider.body2': '. To switch, edit ',
    'settings.provider.body3': ' in your .env and restart the server.',

    'settings.theme.title': '🎨 Theme',
    'settings.theme.body': 'Click 🌓 in the top-right to toggle dark / light. Saved in your browser.',

    'settings.report.title': '📊 Weekly report',
    'settings.report.btn': 'Generate this week\'s report',
    'settings.report.btnLoading': 'Generating…',
    'settings.report.meta': '{newCount} new problems · {reviewCount} card reviews',

    // English-practice page
    'english.title': 'English Practice',
    'english.inputLabel': 'What do you want to say?',
    'english.inputHint': 'Type in Chinese (or any language). AI gives one natural English phrasing and saves it for spaced review.',
    'english.inputPlaceholder': "e.g. 想问能不能在家工作",
    'english.translateBtn': 'Translate & save',
    'english.latest': 'Just saved',
    'english.todayTitle': "Today's Review",
    'english.dueCount': '{n} due',
    'english.todayEmpty': 'No cards due today. Add a phrase above or check back tomorrow.',
    'english.allCards': 'All cards',
    'english.allEmpty': 'No cards yet. Add your first phrase above.',
    'english.cardPrompt': 'You wanted to say:',
    'english.showAnswer': 'Show natural English',
    'english.reviewedTimes': 'reviewed {n}×',
    'english.editPrompt': 'Your phrase (the prompt you remember):',
    'english.editAnswer': 'Natural English (you can refine the AI output):',
    'english.deleteConfirm': "Delete this card?\n\nPrompt: {q}",
    'english.emptyPrompt': 'Type something first',

    // Lang toggle button labels (shown to switch TO that language)
    'lang.switchTo': '中文',
  },

  zh: {
    'app.title': '📚 LeetCode 训练器',
    'nav.today': '今日复习',
    'nav.add': '添加题目',
    'nav.list': '题目列表',
    'nav.calendar': '日历',
    'nav.english': '英语',
    'nav.settings': '设置',
    'nav.logout': '退出',
    'theme.toggle': '切换主题',

    'common.save': '保存',
    'common.delete': '删除',
    'common.cancel': '取消',
    'common.edit': '编辑',
    'common.loading': '加载中…',
    'common.empty': '暂无内容',
    'common.confirm': '确认',

    'diff.easy': '简单',
    'diff.medium': '中等',
    'diff.hard': '困难',

    'mark.remembered': '记住了 ✅',
    'mark.fuzzy': '模糊 🤔',
    'mark.forgot': '忘了 ❌',

    'login.title': '📚 LeetCode 训练器',
    'login.subtitle': '登录后继续',
    'login.email': '邮箱',
    'login.password': '密码',
    'login.submit': '登录',
    'login.noAccount': '还没有账号？',
    'login.register': '注册',
    'login.errBadCreds': '邮箱或密码错误。',
    'register.title': '📚 创建你的账号',
    'register.subtitle': '开始追踪你的 LeetCode 复习',
    'register.confirm': '确认密码',
    'register.submit': '注册',
    'register.pwHint': '至少 6 位。',
    'register.haveAccount': '已有账号？',
    'register.signIn': '去登录',
    'register.mismatch': '两次密码不一致',
    'register.errEmail': '邮箱格式不对。',
    'register.errShort': '密码至少 6 位。',
    'register.errTaken': '该邮箱已注册。',

    'today.title': '今日复习',
    'today.statsLoading': '加载中…',
    'today.stats': '今日待复习 {due} 张，已完成 {done} 张',
    'today.empty': '🎉 今天没有需要复习的卡片，去 ',
    'today.emptyAddLink': '添加新题',
    'today.emptyOrRest': ' 或休息一下。',
    'today.needsGen': '还未生成卡片 →',
    'today.dueCards': '{n} 个知识点待复习 →',

    'add.title': '添加题目',
    'add.editTitle': '编辑题目 #{n}',
    'add.lcNumber': '题号 *',
    'add.titleField': '题目',
    'add.titleHint': '输入题号后会从 LeetCode 自动填充',
    'add.titlePlaceholder': '（输入题号后自动填充）',
    'add.difficulty': '难度',
    'add.tags': '标签',
    'add.tagsEmpty': '（无标签）',
    'add.tagsPlaceholder': '（输入题号后自动填充）',
    'add.lookupBtn': '从 LeetCode 重新拉取元信息',

    'add.q1.label': '① 这道题的思路是否清晰？',
    'add.q1.yes': '是',
    'add.q1.no': '否',
    'add.q1.hint': '选「否」后会要求填写做法描述，AI 出题时必定包含一道「描述这道题的做法」',
    'add.q1.placeholder': '用自己的话描述这道题的核心做法、关键步骤、为什么这样做……\n（不需要写题面，AI 知道）',

    'add.q2.label': '② 语法错误 / 语法要点',
    'add.q2.hint': '写下做这道题时犯过的 Python 语法错误，或不熟悉的写法（每条一行）',
    'add.q2.placeholder': '例：\n- collections.Counter 的 most_common() 返回 list of tuples\n- 用 \'\'.join(sorted(s)) 而不是 sorted(s).join(\'\')\n- defaultdict(list) 不能用 dict 字面量初始化',

    'add.q3.label': '③ 写法优化',
    'add.q3.hint': '不算错但可以更好的写法（空间、可读性、Pythonic 表达等）',
    'add.q3.placeholder': '例：\n- 用数组 cur_max[i] 存每位是多余的，单变量 cur_max 就够，O(n)→O(1)\n- range(1, n) + 单独处理 nums[0] 可简化为 range(0, n) 配合初始值 0',

    'add.q4.label': '④ 其他备注（可选，支持 Markdown）',
    'add.q4.hint': '不属于上面三类的内容：题面、follow-up、面试感悟……',
    'add.q4.placeholder': '## 题面\n...\n\n## Follow-up\n...',

    'add.q5.label': '⑤ 私人笔记',
    'add.q5.badge': '不会被 AI 拿去出题',
    'add.q5.hint': '想记下来但不希望被 AI 拿去出题的内容——比如如何用英文阐述这道题、个人感受、软性笔记。',
    'add.q5.placeholder': '例：\n- 英文阐述：Group strings that are anagrams using sorted-string as canonical key\n- mock 面试时这道题表现不佳，想重做',

    'add.btnSave': '保存',
    'add.btnGoReview': '前往复习页 →',
    'add.btnDelete': '删除',

    'add.toast.added': '已添加，可去复习页生成卡片',
    'add.toast.saved': '已保存',
    'add.toast.deleted': '已删除',
    'add.toast.titleRequired': '题号和标题必填',
    'add.toast.metaRequired': '请先输入题号让系统自动填充元信息',
    'add.toast.descRequired': '选了「思路不清晰」，请填写做法描述',
    'add.toast.fillNumberFirst': '先填题号',
    'add.toast.editLockedMeta': '编辑模式不能改题目元信息',
    'add.toast.lookupOk': '已自动填入 LC {n}: {title}',
    'add.toast.deleteConfirm': '确定删除这道题？相关卡片和复习历史也会一起删除。',

    'list.title': '题目列表',
    'list.count': '共 {n} 题',
    'list.filter.allDiff': '全部难度',
    'list.filter.tagPlaceholder': '标签筛选',
    'list.sort.lcNumber': '题号',
    'list.sort.firstSolved': '首次完成',
    'list.sort.nextReview': '下次复习',
    'list.sort.reviewCount': '复习次数',
    'list.sort.difficulty': '难度',
    'list.sort.updated': '最近更新',
    'list.sort.asc': '升序 ↑',
    'list.sort.desc': '降序 ↓',
    'list.col.num': '#',
    'list.col.title': '题目',
    'list.col.diff': '难度',
    'list.col.tags': '标签',
    'list.col.reviews': '已复习',
    'list.col.next': '下次复习',
    'list.col.actions': '操作',
    'list.action.review': '复习',
    'list.action.edit': '编辑',
    'list.empty': '暂无数据，去 ',
    'list.emptyAddLink': '添加第一道题',
    'list.emptyTail': ' 吧。',

    'review.editNotes': '编辑笔记',
    'review.cards.title': '🎯 知识点测验',
    'review.cards.stats': '{total} 张卡片 · {due} 张到期',
    'review.cards.genFirst': '🤖 AI 生成卡片',
    'review.cards.genMore': '🤖 再生成几张',
    'review.cards.empty': '还没有任何卡片，点上方「AI 生成卡片」让模型基于你的笔记出题。',
    'review.cards.allCaughtUp': '✨ 当前没有到期的卡片，可以稍后再来。',
    'review.cards.futureToggle': '▸ 未到期卡片（{n}）',
    'review.cards.futureToggleOpen': '▾ 未到期卡片（{n}）',
    'review.cards.reviewedTimes': '已复习 {n} 次 · 下次：{date}',
    'review.cards.approachFirst': '🔒 先回忆并描述解题思路 — 完成后其他卡片自动显示。',
    'review.cards.showHint': '💡 提示',
    'review.cards.showAnswer': '显示答案',
    'review.cards.editBtn': '编辑',
    'review.cards.deleteBtn': '删除',

    'review.notes.title': '📝 学习记录',
    'review.notes.empty': '暂无学习记录，去 ',
    'review.notes.editLink': '编辑页',
    'review.notes.q1Clear': '① 思路',
    'review.notes.q1Unclear': '① 思路（用户标记为不清晰）',
    'review.notes.q1Mastered': '✓ 已掌握',
    'review.notes.q1NotFilled': '(未填)',
    'review.notes.q2': '② 语法错误 / 语法要点',
    'review.notes.q3': '③ 写法优化',
    'review.notes.q4': '④ 其他备注',
    'review.notes.q5': '⑤ 私人笔记',
    'review.notes.q5Badge': 'AI 不可见',

    'review.toast.recorded': '已记录',
    'review.toast.generated': '生成了 {n} 张卡片',
    'review.toast.cardSaved': '已保存',
    'review.toast.cardDeleted': '已删除',
    'review.prompt.editQuestion': '问题：',
    'review.prompt.editHint': '提示（可留空）：',
    'review.prompt.editAnswer': '参考答案（支持 Markdown）：',
    'review.prompt.deleteCard': '确定删除这张卡片？\n\n问题：{q}',
    'review.btn.generating': '生成中…',

    'calendar.title': '复习日历',
    'calendar.todayBtn': '今天',
    'calendar.dayHeader.mon': '一',
    'calendar.dayHeader.tue': '二',
    'calendar.dayHeader.wed': '三',
    'calendar.dayHeader.thu': '四',
    'calendar.dayHeader.fri': '五',
    'calendar.dayHeader.sat': '六',
    'calendar.dayHeader.sun': '日',
    'calendar.cellCardCount': '{n} 张',
    'calendar.dayTitle': '{date}（{problems} 题 · {cards} 张卡片）',
    'calendar.dayCards': '{n} 张卡片',
    'calendar.dayEmpty': '这天没有需要复习的卡片。',
    'calendar.month': '{year} 年 {month} 月',

    'settings.title': '设置',
    'settings.intervals.title': '📐 复习间隔（天，逗号分隔）',
    'settings.intervals.hint': '每次"记住了"前进一档，"忘了"回到第一档；实际间隔会再乘以熟练度系数。',
    'settings.intervals.save': '保存',
    'settings.intervals.saved': '已保存',
    'settings.intervals.invalid': '至少填一个非负整数',

    'settings.provider.title': '🤖 AI 提供商',
    'settings.provider.body1': '当前使用：',
    'settings.provider.body2': '。切换请编辑 ',
    'settings.provider.body3': ' 中的 AI_PROVIDER 后重启服务。',

    'settings.theme.title': '🎨 主题',
    'settings.theme.body': '点击右上角 🌓 切换深 / 浅色，偏好会保存在浏览器。',

    'settings.report.title': '📊 周报',
    'settings.report.btn': '生成本周报告',
    'settings.report.btnLoading': '生成中…',
    'settings.report.meta': '本周新做 {newCount} 题 · 复习 {reviewCount} 次',

    'english.title': '英语练习',
    'english.inputLabel': '你想表达什么？',
    'english.inputHint': '输入中文（或任何语言）。AI 给一句地道英文并存为复习卡片。',
    'english.inputPlaceholder': '例：想问能不能在家工作',
    'english.translateBtn': '翻译并保存',
    'english.latest': '已保存',
    'english.todayTitle': '今日复习',
    'english.dueCount': '{n} 张待复习',
    'english.todayEmpty': '今天没有要复习的卡片。在上方添加新句子，或明天再来。',
    'english.allCards': '所有卡片',
    'english.allEmpty': '还没有卡片，去上方添加第一句吧。',
    'english.cardPrompt': '你想说的是：',
    'english.showAnswer': '显示地道说法',
    'english.reviewedTimes': '已复习 {n} 次',
    'english.editPrompt': '你的中文意图：',
    'english.editAnswer': '地道英文（可以修正 AI 的输出）：',
    'english.deleteConfirm': '确定删除这张卡片？\n\n意图：{q}',
    'english.emptyPrompt': '请先输入内容',

    'lang.switchTo': 'EN',
  },
};

function getLang() {
  return localStorage.getItem('lang') || 'en';
}

function setLang(lang) {
  if (lang !== 'en' && lang !== 'zh') return;
  localStorage.setItem('lang', lang);
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  applyI18n();
  window.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
}

function t(key, params, fallback) {
  const dict = I18N_DICT[getLang()] || I18N_DICT.en;
  let s = dict[key] !== undefined ? dict[key] : (fallback !== undefined ? fallback : key);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      s = s.split('{' + k + '}').join(v);
    }
  }
  return s;
}

function applyI18n(root) {
  root = root || document;
  const dict = I18N_DICT[getLang()] || I18N_DICT.en;

  root.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    if (dict[key] !== undefined) el.textContent = dict[key];
  });
  root.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.dataset.i18nHtml;
    if (dict[key] !== undefined) el.innerHTML = dict[key];
  });
  root.querySelectorAll('[data-i18n-attr]').forEach(el => {
    el.dataset.i18nAttr.split(';').forEach(pair => {
      const idx = pair.indexOf(':');
      if (idx < 0) return;
      const attr = pair.slice(0, idx).trim();
      const key = pair.slice(idx + 1).trim();
      if (dict[key] !== undefined) el.setAttribute(attr, dict[key]);
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // Apply translations to whatever's on the page
  document.documentElement.lang = getLang() === 'zh' ? 'zh-CN' : 'en';
  applyI18n();

  // Wire up the language toggle in the nav, if present
  const btn = document.getElementById('lang-toggle');
  if (btn) {
    btn.addEventListener('click', () => {
      setLang(getLang() === 'en' ? 'zh' : 'en');
    });
    const updateLabel = () => { btn.textContent = t('lang.switchTo'); };
    updateLabel();
    window.addEventListener('langchange', updateLabel);
  }
});

window.LT_I18N = { t, setLang, getLang, applyI18n };
