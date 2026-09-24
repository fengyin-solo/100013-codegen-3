<template>
  <section class="page" data-module="setting">
    <header class="page-head">
      <div>
        <h2>系统设置管理</h2>
        <p class="page-desc">维护系统参数。冷藏车准用规则参数修改后先进入待生效，执行「生效参数」后立即参与车辆准用判定，刷新车辆列表即可看到新口径。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记系统参数</button>
        <button class="btn" type="button" @click="exportRows">导出系统设置清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span :class="['tag', statusTagClass(String(row.status ?? ''))]">{{ row.status ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">修改参数</button>
            <button
              class="link"
              type="button"
              :disabled="row.status !== '待生效'"
              :title="row.status !== '待生效' ? '仅待生效参数可以回滚' : ''"
              @click="runAction('回滚参数', row)"
            >
              回滚参数
            </button>
            <button
              class="link"
              type="button"
              :disabled="row.status !== '待生效'"
              :title="row.status !== '待生效' ? '仅待生效参数需要生效' : ''"
              @click="runAction('生效参数', row)"
            >
              生效参数
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">
            当前筛选条件下没有系统参数，可调整检索条件或先登记系统参数
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条系统设置记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 修改参数弹窗：保存后参数进入待生效，再点「生效参数」才会被冷藏车准用规则读取 -->
    <div v-if="editing" class="modal-mask" @click.self="editing = null">
      <div class="modal-panel" role="dialog" aria-modal="true">
        <header class="modal-head">
          <h3>修改系统参数</h3>
          <button class="link" type="button" @click="editing = null">关闭</button>
        </header>
        <dl class="detail-grid">
          <dt>参数编码</dt>
          <dd>{{ editing['参数编码'] }}</dd>
          <dt>参数名称</dt>
          <dd>{{ editing['参数名称'] }}</dd>
          <dt>当前参数值</dt>
          <dd>{{ editing['参数值'] }}（{{ editing.status }}）</dd>
        </dl>
        <label class="filter-item edit-value">
          <span>新的参数值</span>
          <textarea v-model="editValue" rows="3" placeholder="区间类参数填写「下限-上限」，如 5-15；白名单用逗号分隔多个型号"></textarea>
        </label>
        <p class="edit-hint">保存修改后参数进入「待生效」，需在列表中执行「生效参数」才会按新值判定冷藏车准用条件；执行「回滚参数」可恢复本次修改前的值。</p>
        <footer class="modal-foot">
          <button class="btn ghost" type="button" @click="editing = null">取消</button>
          <button class="btn primary" type="button" :disabled="!editValue.trim()" @click="submitEdit">保存修改</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/setting'
const columns = ['参数编码', '参数名称', '参数值', '参数类型', '生效范围', '修改人']
const statuses = ['已生效', '待生效', '已回滚']
const stats = [{ label: '生效参数', value: 0 }, { label: '待生效参数', value: 0 }, { label: '本周变更次数', value: 0 }]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const editing = ref<Row | null>(null)
const editValue = ref('')

function statusTagClass(status: string) {
  if (status === '已生效') return 'tag-ok'
  if (status === '待生效') return 'tag-warn'
  return 'tag-muted'
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '系统参数登记入口尚未接入审批流'
}

function openEdit(row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  editing.value = row
  editValue.value = String(row['参数值'] ?? '')
}

async function submitEdit() {
  if (!editing.value) return
  const target = editing.value
  editing.value = null
  await runAction('修改参数', target, { 参数值: editValue.value.trim() })
}

async function runAction(action: string, row: Row, extra: Record<string, string> = {}) {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...extra } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '系统设置动作未生效，请稍后重试')
    }
    successMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统设置操作失败'
  }
}

async function reload() {
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('系统参数列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统设置列表读取失败'
  }
}

onMounted(reload)
</script>
