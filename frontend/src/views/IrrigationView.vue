<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

// list 始终是“东八区今日”轮灌（与仪表盘同一归日口径，由后端 today=1 过滤）。
const list = ref([])
const zones = ref([])
const dashboard = ref(null)
const error = ref('')
const editingId = ref(null)
const filterStatus = ref('')

function localInputValue(d = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const form = reactive({
  zoneId: '',
  startAt: localInputValue(),
  durationMin: 30,
  waterLiters: 100,
  status: 'scheduled',
})

const statusLabel = {
  scheduled: '已排程',
  running: '进行中',
  done: '已完成',
  skipped: '已跳过',
}

// 两侧数字都以“分”为整数比较，规避浮点误差。
function toCents(v) {
  return Math.round(Number(v || 0) * 100)
}

// 列表侧：今日列表 waterLiters 加总（累加器统一为整数分）。
const listLiters = computed(() =>
  list.value.reduce((cents, row) => cents + toCents(row.waterLiters), 0) / 100
)
// 仪表盘侧：服务端单次聚合的今日升数。
const dashboardLiters = computed(() =>
  Number(dashboard.value?.irrigationTodayLiters || 0)
)
const aligned = computed(() => toCents(listLiters.value) === toCents(dashboardLiters.value))

// 状态筛选只影响表格展示，不参与“今日加总”。
const visibleList = computed(() =>
  filterStatus.value ? list.value.filter((r) => r.status === filterStatus.value) : list.value
)

function resetForm() {
  editingId.value = null
  form.zoneId = zones.value[0]?.id || ''
  form.startAt = localInputValue()
  form.durationMin = 30
  form.waterLiters = 100
  form.status = 'scheduled'
}

async function loadZones() {
  const { data } = await api.get('/zones/')
  zones.value = data.results || data
  if (!form.zoneId && zones.value.length) form.zoneId = zones.value[0].id
}

// 一次性并行重取两侧：今日列表 + 仪表盘统计。任何增删改后立即调用。
async function load() {
  error.value = ''
  try {
    const [listRes, dashRes] = await Promise.all([
      api.get('/irrigation-cycles/', { params: { today: '1' } }),
      api.get('/dashboard/'),
    ])
    list.value = listRes.data.results || listRes.data
    dashboard.value = dashRes.data
  } catch {
    error.value = '加载今日轮灌失败'
  }
}

function edit(row) {
  editingId.value = row.id
  form.zoneId = row.zoneId
  form.startAt = localInputValue(new Date(row.startAt))
  form.durationMin = row.durationMin
  form.waterLiters = Number(row.waterLiters)
  form.status = row.status
}

async function save() {
  error.value = ''
  const payload = {
    zoneId: Number(form.zoneId),
    startAt: new Date(form.startAt).toISOString(),
    durationMin: form.durationMin,
    waterLiters: form.waterLiters,
    status: form.status,
  }
  try {
    if (editingId.value) {
      await api.put(`/irrigation-cycles/${editingId.value}/`, payload)
    } else {
      await api.post('/irrigation-cycles/', payload)
    }
    resetForm()
    // 改完水量马上重取两侧，结果必须仍对齐。
    await load()
  } catch (e) {
    error.value = JSON.stringify(e.response?.data || '保存失败')
  }
}

async function remove(id) {
  if (!confirm('确认删除该轮灌记录？')) return
  await api.delete(`/irrigation-cycles/${id}/`)
  await load()
}

onMounted(async () => {
  await loadZones()
  await load()
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>轮灌计划</h1>
        <p>按分区安排起灌时间、时长与水量（列表按东八区今日过滤）</p>
      </div>
      <div class="actions">
        <select v-model="filterStatus">
          <option value="">全部状态</option>
          <option value="scheduled">已排程</option>
          <option value="running">进行中</option>
          <option value="done">已完成</option>
          <option value="skipped">已跳过</option>
        </select>
      </div>
    </div>

    <div class="stats">
      <div class="stat">
        <div class="label">仪表盘今日轮灌水量</div>
        <div class="value">{{ dashboardLiters.toFixed(2) }} L</div>
      </div>
      <div class="stat">
        <div class="label">今日列表水量加总</div>
        <div class="value">{{ listLiters.toFixed(2) }} L</div>
      </div>
      <div class="stat">
        <div class="label">两侧校验</div>
        <div class="value" :style="{ color: aligned ? 'var(--green, #2e7d32)' : '#c62828' }">
          {{ aligned ? '✓ 一致' : '✗ 不一致' }}
        </div>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">{{ editingId ? '编辑轮灌' : '新建轮灌' }}</h3>
      <div class="form-grid">
        <label>
          分区
          <select v-model="form.zoneId">
            <option v-for="z in zones" :key="z.id" :value="z.id">
              {{ z.greenhouseName }} / {{ z.zoneCode }}
            </option>
          </select>
        </label>
        <label>开始时间<input v-model="form.startAt" type="datetime-local" /></label>
        <label>时长(分钟)<input v-model.number="form.durationMin" type="number" min="1" /></label>
        <label>水量(升)<input v-model.number="form.waterLiters" type="number" step="0.01" min="0" /></label>
        <label>
          状态
          <select v-model="form.status">
            <option value="scheduled">已排程</option>
            <option value="running">进行中</option>
            <option value="done">已完成</option>
            <option value="skipped">已跳过</option>
          </select>
        </label>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="actions" style="margin-top:12px">
        <button class="btn" @click="save">保存</button>
        <button v-if="editingId" class="btn ghost" @click="resetForm">取消编辑</button>
      </div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>开始</th>
            <th>温室/分区</th>
            <th>时长</th>
            <th>水量</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in visibleList" :key="row.id">
            <td>{{ new Date(row.startAt).toLocaleString() }}</td>
            <td>{{ row.greenhouseName }} / {{ row.zoneCode }}</td>
            <td>{{ row.durationMin }} 分</td>
            <td>{{ row.waterLiters }} L</td>
            <td>
              <span class="badge" :class="row.status">{{ statusLabel[row.status] || row.status }}</span>
            </td>
            <td class="actions">
              <button class="btn ghost" @click="edit(row)">编辑</button>
              <button class="btn danger" @click="remove(row.id)">删除</button>
            </td>
          </tr>
          <tr v-if="!visibleList.length">
            <td colspan="6" style="text-align:center;color:var(--muted)">东八区今日暂无轮灌记录</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
