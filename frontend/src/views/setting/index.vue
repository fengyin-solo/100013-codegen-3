<template>
  <section class="page" data-module="setting">
    <header class="page-head">
      <div>
        <h2>系统设置</h2>
        <p class="page-desc">维护系统参数，围绕参数编码、参数名称、参数值做登记、筛选与状态流转；冷藏车准用规则参数调整后立即生效。</p>
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
          <td v-for="column in columns" :key="column" :class="{ 'reason-cell': column === '参数值' }">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">修改参数值</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无系统设置数据，可先登记系统参数</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条系统设置记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="editing" class="modal-mask" @click.self="closeEdit">
      <div class="modal" role="dialog" aria-modal="true" aria-label="修改系统参数">
        <div class="modal-head">
          <h3>修改参数值</h3>
          <button class="btn ghost" type="button" @click="closeEdit">关闭</button>
        </div>
        <div class="detail-grid">
          <div class="detail-item detail-item-wide">
            <span class="detail-label">参数编码</span>
            <span class="detail-value">{{ editing['参数编码'] }}</span>
          </div>
          <div class="detail-item detail-item-wide">
            <span class="detail-label">参数名称</span>
            <span class="detail-value">{{ editing['参数名称'] }}</span>
          </div>
        </div>
        <label class="form-block">
          <span class="detail-label">参数值</span>
          <textarea v-model="editValue" rows="8" class="form-textarea" placeholder="请输入参数值；JSON 参数需填写合法 JSON"></textarea>
        </label>
        <p v-if="isJsonParam" class="detail-tip">该参数为 JSON 配置，保存时会校验格式；保存后刷新冷藏车列表即按新规则判定，无需重启服务。</p>
        <p v-if="editError" class="error-text">{{ editError }}</p>
        <div class="modal-foot">
          <button class="btn" type="button" :disabled="saving" @click="closeEdit">取消</button>
          <button class="btn primary" type="button" :disabled="saving" @click="saveEdit">
            {{ saving ? '保存中…' : '保存并生效' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/setting'
const columns = ["参数编码", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]
const actions = ["修改参数", "回滚参数", "生效参数"]
const stats = [{"label": "生效参数", "value": 0}, {"label": "待生效参数", "value": 0}, {"label": "本周变更次数", "value": 0}]
const JSON_PARAM_CODES = ['VEHICLE_VOLUME_RULES', 'VEHICLE_UNIT_WHITELIST']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const editing = ref<Row | null>(null)
const editValue = ref('')
const editError = ref('')
const saving = ref(false)

const isJsonParam = computed(() =>
  editing.value !== null && JSON_PARAM_CODES.includes(String(editing.value['参数编码'])),
)

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
  editing.value = row
  editValue.value = String(row['参数值'] ?? '')
  editError.value = ''
}

function closeEdit() {
  if (saving.value) {
    return
  }
  editing.value = null
  editValue.value = ''
  editError.value = ''
}

async function saveEdit() {
  if (!editing.value) {
    return
  }
  editError.value = ''
  if (!editValue.value.trim()) {
    editError.value = '参数值不能为空'
    return
  }
  if (isJsonParam.value) {
    try {
      JSON.parse(editValue.value)
    } catch {
      editError.value = '参数值不是合法 JSON，请检查后再保存'
      return
    }
  }
  saving.value = true
  try {
    const response = await request(`${ENDPOINT}/${editing.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ values: { '参数值': editValue.value } }),
    })
    if (!response.ok) {
      throw new Error('系统参数保存失败，请稍后重试')
    }
    const payload = (await response.json()) as { ok?: boolean; message?: string }
    if (payload.ok === false) {
      editError.value = payload.message ?? '系统参数保存失败'
      return
    }
    editing.value = null
    editValue.value = ''
    await reload()
  } catch (error) {
    editError.value = error instanceof Error ? error.message : '系统参数保存失败'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('系统设置动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as { ok?: boolean; message?: string }
    if (payload.ok === false) {
      errorMessage.value = payload.message ?? '系统设置动作未生效'
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '系统设置操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
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
