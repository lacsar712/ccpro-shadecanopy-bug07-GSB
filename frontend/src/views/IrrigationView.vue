<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const list = ref([])
const zones = ref([])
const error = ref('')
const editingId = ref(null)
const filterStatus = ref('')
// 列表默认只看「今日」，与看板共用东八区归日口径
const onlyToday = ref(true)

// 两侧数据：今日列表加总 vs 看板今日升数 —— 每次都实时重取，禁止本地缓存
const listTodayLiters = ref(0)
const dashboardTodayLiters = ref(null)
const aligned = computed(
  () =>
    dashboardTodayLiters.value !== null &&
    Number(listTodayLiters.value) === Number(dashboardTodayLiters.value)
)

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

async function loadTodayList() {
  // 今日轮灌：后端按东八区归日且不分页，不过滤状态，加总即看板今日升数
  const { data } = await api.get('/irrigation-cycles/', {
    params: { today: 1 },
  })
  const rows = data.results || data
  listTodayLiters.value = rows.reduce(
    (sum, r) => sum + Number(r.waterLiters || 0),
    0
  )
  return rows
}

async function loadDashboard() {
  const { data } = await api.get('/dashboard/')
  dashboardTodayLiters.value = Number(data.irrigationTodayLiters || 0)
  return data
}

async function refreshBoth() {
  // 改完水量后两侧并行实时重取，不使用任何缓存数字
  const [todayRows] = await Promise.all([loadTodayList(), loadDashboard()])
  return todayRows
}

async function load() {
  error.value = ''
  try {
    // 每次加载都实时重取两侧（保存/改水量/删除后同样走这里），不用缓存
    const todayRows = await refreshBoth()
    if (onlyToday.value) {
      // 今日行已取到；状态筛选在今日集合内做本地过滤，加总始终用全量今日行
      list.value = filterStatus.value
        ? todayRows.filter((r) => r.status === filterStatus.value)
        : todayRows
    } else {
      const params = {}
      if (filterStatus.value) params.status = filterStatus.value
      const { data } = await api.get('/irrigation-cycles/', { params })
      list.value = data.results || data
    }
  } catch {
    error.value = '加载轮灌计划失败'
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
        <p>按分区安排起灌时间、时长与水量（今日按东八区归日）</p>
      </div>
      <div class="actions">
        <label style="display:flex;align-items:center;gap:6px">
          <input v-model="onlyToday" type="checkbox" @change="load" /> 仅今日
        </label>
        <select v-model="filterStatus" @change="load">
          <option value="">全部状态</option>
          <option value="scheduled">已排程</option>
          <option value="running">进行中</option>
          <option value="done">已完成</option>
          <option value="skipped">已跳过</option>
        </select>
      </div>
    </div>

    <div class="panel" v-if="onlyToday">
      <div class="stats" style="margin:0">
        <div class="stat">
          <div class="label">今日列表水量加总</div>
          <div class="value">{{ listTodayLiters }} L</div>
        </div>
        <div class="stat">
          <div class="label">看板今日升数</div>
          <div class="value">{{ dashboardTodayLiters ?? '—' }} L</div>
        </div>
        <div class="stat">
          <div class="label">口径校验</div>
          <div class="value" :style="{ color: aligned ? 'var(--ok, #2e7d32)' : '#c62828' }">
            {{ aligned ? '一致 ✓' : '不一致 ✗' }}
          </div>
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
          <tr v-for="row in list" :key="row.id">
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
        </tbody>
      </table>
    </div>
  </div>
</template>
