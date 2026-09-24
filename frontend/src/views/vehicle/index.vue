<template>
  <section class="page" data-module="vehicle">
    <header class="page-head">
      <div>
        <h2>冷藏车管理管理</h2>
        <p class="page-desc">维护冷藏车辆，围绕车牌号码、车辆类型、制冷机组型号、车厢容积做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记冷藏车辆</button>
        <button class="btn" type="button" @click="exportRows">导出冷藏车管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statsCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <!-- 当前生效的准用规则摘要：规则随系统参数调整，刷新后按新口径展示 -->
    <section v-if="rules" class="rule-banner">
      <div class="rule-banner-head">
        <strong>当前车辆准用条件</strong>
        <button class="link" type="button" @click="reload">刷新规则</button>
      </div>
      <ul class="rule-list">
        <li>已停用车辆不允许安排出车</li>
        <li>制冷机组型号需在白名单内：{{ rules.unitWhitelist.join('、') }}</li>
        <li v-for="range in rules.volumeRanges" :key="range.vehicleType">
          {{ range.vehicleType }}车厢容积需在 {{ range.min }}~{{ range.max }}m³ 之间
        </li>
      </ul>
      <template v-if="rules.warnings.length">
        <p v-for="warning in rules.warnings" :key="warning" class="rule-warning">
          ⚠ {{ warning }}
        </p>
      </template>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>车牌号码</span>
        <input v-model="filters.keyword" placeholder="按车牌号码检索" />
      </label>
      <label class="filter-item">
        <span>车辆状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>准用状态</span>
        <select v-model="filters.eligible">
          <option value="">全部车辆</option>
          <option value="true">只看准予出车</option>
          <option value="false">只看限制出车</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>准用状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '车牌号码'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td>
            <span :class="['tag', isEligible(row) ? 'tag-ok' : 'tag-block']">
              {{ isEligible(row) ? '准予出车' : '限制出车' }}
            </span>
            <p v-if="!isEligible(row)" class="cell-note">{{ row['准用说明'] }}</p>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="action === '安排出车' && !isEligible(row)"
              :title="action === '安排出车' && !isEligible(row) ? String(row['准用说明'] ?? '') : ''"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条冷藏车管理记录，其中 {{ eligibleTotal }} 台满足准用条件</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 车辆详情抽屉：完整字段 + 准用判定说明 + 判定所依据的规则口径 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal-panel detail-panel" role="dialog" aria-modal="true">
        <header class="modal-head">
          <h3>冷藏车辆详情 · {{ detail['车牌号码'] }}</h3>
          <button class="link" type="button" @click="detail = null">关闭</button>
        </header>
        <div :class="['detail-verdict', isEligible(detail) ? 'verdict-ok' : 'verdict-block']">
          <strong>{{ isEligible(detail) ? '✓ 准予出车' : '✕ 限制出车' }}</strong>
          <p>{{ detail['准用说明'] }}</p>
          <ul v-if="reasons(detail).length" class="reason-list">
            <li v-for="reason in reasons(detail)" :key="reason">{{ reason }}</li>
          </ul>
        </div>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </template>
          <dt>当前状态</dt>
          <dd>{{ detail.status ?? '—' }}</dd>
        </dl>
        <section v-if="detail.rules" class="detail-rules">
          <p class="detail-rules-title">判定所依据的当前生效规则（可在系统设置中调整）：</p>
          <ul class="rule-list">
            <li>已停用车辆不允许安排出车</li>
            <li>制冷机组白名单：{{ detail.rules.unitWhitelist.join('、') }}</li>
            <li v-for="range in detail.rules.volumeRanges" :key="range.vehicleType">
              {{ range.vehicleType }}：{{ range.min }}~{{ range.max }}m³
            </li>
          </ul>
        </section>
        <footer class="modal-foot">
          <button
            v-for="action in actions"
            :key="action"
            class="btn"
            :class="{ primary: action === '安排出车' }"
            type="button"
            :disabled="action === '安排出车' && !isEligible(detail)"
            @click="runAction(action, detail)"
          >
            {{ action }}
          </button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Rules = {
  unitWhitelist: string[]
  volumeRanges: Array<{ vehicleType: string; min: number; max: number }>
  warnings: string[]
}
type RowValue = string | number | boolean | string[] | Rules | undefined | null
type Row = Record<string, RowValue>
interface VehicleDetail extends Record<string, RowValue> {
  id: string | number
  rules?: Rules
}

const ENDPOINT = '/api/vehicle'
const columns = ['车牌号码', '车辆类型', '制冷机组型号', '车厢容积', '温区数量', '所属车队', '年检到期日']
const actions = ['安排出车', '回场登记', '停用车辆']
const statuses = ['可用', '出车中', '维修中', '已停用']

const rows = ref<Row[]>([])
const total = ref(0)
const eligibleTotal = ref(0)
const errorMessage = ref('')
const rules = ref<Rules | null>(null)
const detail = ref<VehicleDetail | null>(null)
const filters = ref({ keyword: '', status: '', eligible: '' })

const statsCards = computed(() => [
  { label: '全部车辆', value: total.value },
  { label: '准予出车', value: eligibleTotal.value },
  { label: '限制出车', value: total.value - eligibleTotal.value },
])

const hasFilter = computed(() =>
  Boolean(filters.value.keyword.trim() || filters.value.status || filters.value.eligible),
)

const emptyText = computed(() =>
  hasFilter.value
    ? '当前筛选条件下没有符合条件的车辆，可放宽车牌、状态或准用条件后重试'
    : '暂无冷藏车辆档案，可先登记冷藏车辆',
)

function isEligible(row: Row): boolean {
  return row['准用状态'] === '准予出车'
}

function reasons(row: Row): string[] {
  return Array.isArray(row['准用原因']) ? (row['准用原因'] as string[]) : []
}

function resetFilters() {
  filters.value = { keyword: '', status: '', eligible: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '冷藏车辆登记入口尚未接入审批流'
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('冷藏车辆详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏车辆详情读取失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '安排出车' && !isEligible(row)) {
    errorMessage.value = String(row['准用说明'] ?? '该车辆不满足准用条件，无法安排出车')
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '冷藏车管理动作未生效，请稍后重试')
    }
    await reload()
    if (detail.value && String(detail.value.id) === String(row.id)) {
      await openDetail(payload.entry ?? row)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏车管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (filters.value.keyword.trim()) params.set('keyword', filters.value.keyword.trim())
  if (filters.value.status) params.set('status', filters.value.status)
  if (filters.value.eligible) params.set('eligible', filters.value.eligible)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('冷藏车辆列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    eligibleTotal.value = payload.eligibleTotal ?? 0
    rules.value = payload.rules ?? null
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏车管理列表读取失败'
  }
}

onMounted(reload)
</script>
