<template>
  <section class="page" data-module="vehicle">
    <header class="page-head">
      <div>
        <h2>冷藏车管理</h2>
        <p class="page-desc">维护冷藏车辆，围绕车牌号码、车辆类型、制冷机组型号、车厢容积做登记、筛选与状态流转；出车准用条件由系统参数配置。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记冷藏车辆</button>
        <button class="btn" type="button" @click="exportRows">导出冷藏车管理清单</button>
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
      <label class="filter-item">
        <span>出车准用</span>
        <select v-model="dispatchableFilter">
          <option value="">全部</option>
          <option value="true">可出车</option>
          <option value="false">限制出车</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>出车准用</th>
          <th>准用说明</th>
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
            <span class="badge" :class="row['准用状态'] === '可出车' ? 'badge-ok' : 'badge-block'">
              {{ row['准用状态'] }}
            </span>
          </td>
          <td class="reason-cell">{{ row['准用说明'] ?? '—' }}</td>
          <td class="row-actions">
            <template v-for="action in actions" :key="action">
              <button
                v-if="action !== '安排出车' || row['准用状态'] === '可出车'"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <span
                v-else
                class="link link-disabled"
                :title="String(row['准用说明'] ?? '')"
              >{{ action }}</span>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 3" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条冷藏车管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal" role="dialog" aria-modal="true" aria-label="冷藏车辆详情">
        <div class="modal-head">
          <h3>冷藏车辆详情</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </div>
        <div class="detail-grid">
          <div v-for="field in detailFields" :key="field" class="detail-item">
            <span class="detail-label">{{ field }}</span>
            <span class="detail-value">{{ detail[field] ?? '—' }}</span>
          </div>
          <div class="detail-item detail-item-wide">
            <span class="detail-label">出车准用</span>
            <span class="detail-value">
              <span class="badge" :class="detail['准用状态'] === '可出车' ? 'badge-ok' : 'badge-block'">
                {{ detail['准用状态'] }}
              </span>
            </span>
          </div>
          <div class="detail-item detail-item-wide">
            <span class="detail-label">准用说明</span>
            <span class="detail-value" :class="{ 'error-text': detail['准用状态'] !== '可出车' }">
              {{ detail['准用说明'] }}
            </span>
          </div>
        </div>
        <p class="detail-tip">准用条件由系统参数「VEHICLE_VOLUME_RULES」「VEHICLE_UNIT_WHITELIST」配置，并与车辆停用状态合并判定，参数调整后刷新即可生效。</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/vehicle'
const columns = ["车牌号码", "车辆类型", "制冷机组型号", "车厢容积", "温区数量", "所属车队", "年检到期日"]
const detailFields = ["id", "status", ...columns]
const actions = ["安排出车", "回场登记", "停用车辆"]
const filterFields = columns.slice(0, 3)

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const dispatchableFilter = ref('')
const detail = ref<Row | null>(null)

const stats = computed(() => {
  const eligible = rows.value.filter((row) => row['准用状态'] === '可出车').length
  const blocked = rows.value.length - eligible
  const disabled = rows.value.filter((row) => row.status === '已停用').length
  return [
    { label: '当前页可出车', value: eligible },
    { label: '当前页限制出车', value: blocked },
    { label: '其中已停用', value: disabled },
  ]
})

const emptyText = computed(() => {
  if (dispatchableFilter.value === 'false') {
    return '当前筛选条件下没有限制出车的车辆；如与预期不符，请到「系统设置」检查容积范围与制冷机组白名单参数'
  }
  if (dispatchableFilter.value === 'true') {
    return '没有符合出车准用条件的车辆：可调整筛选条件，或到「系统设置」放宽容积范围、补充制冷机组白名单'
  }
  return '暂无冷藏车管理数据，可先登记冷藏车辆'
})

function resetFilters() {
  filters.value = {}
  dispatchableFilter.value = ''
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

function closeDetail() {
  detail.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('冷藏车管理动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as { ok?: boolean; message?: string }
    if (payload.ok === false) {
      errorMessage.value = payload.message ?? '冷藏车管理动作未生效'
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏车管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams(filters.value as Record<string, string>)
  if (dispatchableFilter.value) {
    params.set('dispatchable', dispatchableFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('冷藏车辆列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '冷藏车管理列表读取失败'
  }
}

onMounted(reload)
</script>
