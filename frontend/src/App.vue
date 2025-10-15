<template>
  <div id="app">
    <el-container>
      <el-header>
        <div class="header-content">
          <h1>📱 微信支付截图 OCR 识别和去重工具</h1>
          <p class="subtitle">使用 Tesseract OCR 识别订单编号并自动去重</p>
        </div>
      </el-header>
      
      <el-main>
        <el-card class="upload-card" v-if="currentStep === 'upload'">
          <template #header>
            <div class="card-header">
              <span>📤 上传文件夹</span>
            </div>
          </template>
          
          <!-- 文件夹上传区域 -->
          <div 
            class="folder-upload-area" 
            @click="triggerFolderSelect"
            @dragover.prevent
            @drop.prevent="handleDrop"
          >
            <input 
              ref="folderInput"
              type="file"
              webkitdirectory
              directory
              multiple
              accept=".jpg,.jpeg,.png,.JPG,.JPEG,.PNG"
              @change="handleFolderSelect"
              style="display: none;"
            >
            <div class="upload-demo">
              <el-icon class="el-icon--upload"><upload-filled /></el-icon>
              <div class="el-upload__text">
                将文件夹拖到此处，或<em>点击选择文件夹</em>
              </div>
              <div class="el-upload__tip">
                支持上传整个文件夹，自动识别其中的 JPG、JPEG、PNG 格式图片
              </div>
            </div>
          </div>
          
          <!-- 手动文件夹选择按钮 -->
          <div class="manual-folder-select">
            <el-button type="primary" @click="triggerFolderSelect" :disabled="uploading">
              📁 手动选择文件夹
            </el-button>
            <span class="folder-tip">如果拖拽不工作，请点击此按钮选择文件夹</span>
          </div>
          
          <div class="upload-actions" v-if="fileList.length > 0">
            <el-button type="primary" @click="uploadFiles" :loading="uploading">
              上传并开始识别 ({{ fileList.length }} 个文件)
            </el-button>
            <el-button @click="clearFiles">清空</el-button>
          </div>
          
          <!-- 文件夹结构预览 -->
          <div v-if="fileList.length > 0" class="folder-preview">
            <el-collapse v-model="activeFolders">
              <el-collapse-item 
                v-for="(folderFiles, folder) in folderStructure" 
                :key="folder"
                :name="folder"
                :title="`📁 ${folder} (${folderFiles.length} 个文件)`"
              >
                <div class="folder-files">
                  <el-tag 
                    v-for="file in folderFiles" 
                    :key="file.name"
                    size="small"
                    class="file-tag"
                  >
                    {{ file.name }}
                  </el-tag>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </el-card>
        
        <el-card class="processing-card" v-if="currentStep === 'processing'">
          <template #header>
            <div class="card-header">
              <span>⚙️ 正在处理中...</span>
            </div>
          </template>
          
          <div class="processing-content">
            <el-progress 
              :percentage="processingProgress"
              :indeterminate="processingProgress === 0"
              :duration="3"
            />
            <p class="processing-text">{{ processingMessage }}</p>
            <p class="processing-tip">正在使用 OCR 识别订单号和金额，请稍候...</p>
          </div>
        </el-card>
        
        <el-card class="result-card" v-if="currentStep === 'completed'">
          <template #header>
            <div class="card-header">
              <span>✅ 处理完成</span>
              <el-button type="primary" @click="downloadResult" :loading="downloading">
                <el-icon><download /></el-icon>
                下载去重后的文件
              </el-button>
              <!-- <el-button type="success" @click="downloadCache" :loading="downloading" style="margin-left: 10px;">
                <el-icon><download /></el-icon>
                下载OCR缓存
              </el-button> -->
            </div>
          </template>
          
          <div class="result-summary">
            <el-row :gutter="20">
              <el-col :span="4">
                <el-statistic title="总文件数" :value="resultData.total_files" />
              </el-col>
              <el-col :span="4">
                <el-statistic title="成功识别" :value="resultData.success_count" />
              </el-col>
              <el-col :span="4">
                <el-statistic title="唯一订单" :value="resultData.unique_orders" />
              </el-col>
              <el-col :span="4">
                <el-statistic title="重复图片" :value="resultData.duplicate_images || 0" />
              </el-col>
              <el-col :span="4">
                <el-statistic title="重复文件数" :value="resultData.total_duplicate_files || 0" />
              </el-col>
              <el-col :span="4">
                <el-statistic title="总金额" :value="resultData.total_amount" prefix="¥" :precision="2" />
              </el-col>
            </el-row>
          </div>
          
          <el-tabs v-model="activeTab" class="result-tabs">
            <el-tab-pane label="订单列表" name="orders">
              <el-table :data="resultData.orders" stripe style="width: 100%" max-height="500">
                <el-table-column prop="index" label="序号" width="80" />
                <el-table-column prop="order_number" label="订单号" min-width="220" />
                <el-table-column prop="amount" label="金额" width="120">
                  <template #default="scope">
                    ¥{{ scope.row.amount.toFixed(2) }}
                  </template>
                </el-table-column>
                <el-table-column prop="folder" label="文件夹" width="150" />
                <el-table-column prop="filename" label="文件名" min-width="200" />
              </el-table>
            </el-tab-pane>
            
            <el-tab-pane label="重复订单" name="duplicates" v-if="resultData.duplicates && resultData.duplicates.length > 0">
              <el-alert
                title="以下是检测到的重复订单，系统已自动去重"
                type="warning"
                show-icon
                :closable="false"
                style="margin-bottom: 15px;"
              />
              <el-collapse v-model="activeDuplicates">
                <el-collapse-item 
                  v-for="dup in resultData.duplicates" 
                  :key="dup.order_number"
                  :name="dup.order_number"
                >
                  <template #title>
                    <div class="duplicate-title">
                      <span class="order-num">{{ dup.order_number }}</span>
                      <el-tag type="warning" size="small">{{ dup.duplicate_count }} 个重复</el-tag>
                      <span class="amount">¥{{ dup.amount.toFixed(2) }}</span>
                    </div>
                  </template>
                  <div class="duplicate-content">
                    <p><strong>保留文件:</strong> {{ dup.original_file }}</p>
                    <p><strong>重复文件:</strong></p>
                    <ul>
                      <li v-for="file in dup.duplicate_files" :key="file">{{ file }}</li>
                    </ul>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>
            
            <el-tab-pane label="重复图片" name="duplicate_images" v-if="resultData.duplicate_images_list && resultData.duplicate_images_list.length > 0">
              <el-alert
                :title="`检测到 ${resultData.duplicate_images_list.length} 组重复图片`"
                type="warning"
                show-icon
                :closable="false"
                style="margin-bottom: 15px;"
              />
              <el-collapse v-model="activeDuplicateImages">
                <el-collapse-item 
                  v-for="(duplicate, index) in resultData.duplicate_images_list" 
                  :key="duplicate.hash"
                  :name="`duplicate_${index}`"
                >
                  <template #title>
                    <div class="duplicate-images-title">
                      <span class="duplicate-group-title">重复图片组 {{ index + 1 }}</span>
                      <el-tag type="warning" size="small">{{ duplicate.count }} 个重复文件</el-tag>
                    </div>
                  </template>
                  <div class="duplicate-images-content">
                    <div class="duplicate-files-list">
                      <div 
                        v-for="(file, fileIndex) in duplicate.files" 
                        :key="fileIndex"
                        class="duplicate-file-item"
                      >
                        <el-icon><picture /></el-icon>
                        <span class="file-name">{{ file }}</span>
                        <el-tag v-if="fileIndex === 0" type="success" size="small">保留</el-tag>
                        <el-tag v-else type="danger" size="small">重复</el-tag>
                      </div>
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>
            
            <el-tab-pane label="识别失败" name="failed" v-if="resultData.failed_files && resultData.failed_files.length > 0">
              <el-alert
                :title="`有 ${resultData.failed_files.length} 个文件识别失败`"
                type="error"
                show-icon
                :closable="false"
                style="margin-bottom: 15px;"
              />
              <el-table :data="failedFilesData" stripe style="width: 100%">
                <el-table-column prop="index" label="序号" width="80" />
                <el-table-column prop="filename" label="文件名" />
              </el-table>
            </el-tab-pane>
          </el-tabs>
          
          <div class="result-actions">
            <el-button @click="resetAll">处理新的文件</el-button>
          </div>
        </el-card>
      </el-main>
      
      <el-footer>
        <div class="footer-content">
          <p>Powered by Tesseract OCR | Flask + Vue3</p>
        </div>
      </el-footer>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Download, Picture } from '@element-plus/icons-vue'
import axios from 'axios'

const currentStep = ref('upload') // upload, processing, completed
const fileList = ref([])
const uploading = ref(false)
const downloading = ref(false)
const taskId = ref(null)
const processingMessage = ref('正在上传文件...')
const processingProgress = ref(0)
const resultData = ref({})
const activeTab = ref('orders')
const activeDuplicates = ref([])
const activeDuplicateImages = ref([])
const activeFolders = ref([])
const folderStructure = ref({})
const folderInput = ref(null)

const failedFilesData = computed(() => {
  if (!resultData.value.failed_files) return []
  return resultData.value.failed_files.map((filename, index) => ({
    index: index + 1,
    filename
  }))
})

const triggerFolderSelect = () => {
  if (folderInput.value) {
    folderInput.value.click()
  }
}

const handleFolderSelect = (event) => {
  console.log('文件夹选择事件触发', event.target.files)
  const files = Array.from(event.target.files)
  console.log('选择的文件数量:', files.length)
  
  // 过滤出图片文件
  const imageFiles = files.filter(f => {
    const name = f.name.toLowerCase()
    return name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.png')
  })
  console.log('图片文件数量:', imageFiles.length)
  
  // 确保文件对象有正确的属性
  const processedFiles = imageFiles.map(file => ({
    ...file,
    raw: file, // 确保有raw属性
    webkitRelativePath: file.webkitRelativePath || file.name
  }))
  
  fileList.value = processedFiles
  
  // 构建文件夹结构
  buildFolderStructure(processedFiles)
  
  // 清空input以便下次选择
  event.target.value = ''
  
  if (imageFiles.length > 0) {
    ElMessage.success(`成功选择 ${imageFiles.length} 个图片文件`)
  } else {
    ElMessage.warning('未找到图片文件，请确保文件夹中包含 JPG、JPEG 或 PNG 格式的图片')
  }
}

const handleDrop = (event) => {
  const items = event.dataTransfer.items
  const files = []
  
  // 处理拖拽的文件
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === 'file') {
      const entry = item.webkitGetAsEntry()
      if (entry) {
        // 如果是文件夹，需要递归处理
        if (entry.isDirectory) {
          traverseFileTree(entry, files)
        } else {
          // 单个文件
          const file = item.getAsFile()
          if (file) files.push(file)
        }
      }
    }
  }
  
  // 延迟处理，等待所有文件收集完成
  setTimeout(() => {
    const imageFiles = files.filter(f => {
      const name = f.name.toLowerCase()
      return name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.png')
    })
    
    // 确保文件对象有正确的属性
    const processedFiles = imageFiles.map(file => ({
      ...file,
      raw: file, // 确保有raw属性
      webkitRelativePath: file.webkitRelativePath || file.name
    }))
    
    fileList.value = processedFiles
    buildFolderStructure(processedFiles)
    
    if (imageFiles.length > 0) {
      ElMessage.success(`成功选择 ${imageFiles.length} 个图片文件`)
    }
  }, 100)
}

const traverseFileTree = (item, files) => {
  if (item.isFile) {
    item.file(file => {
      files.push(file)
    })
  } else if (item.isDirectory) {
    const reader = item.createReader()
    reader.readEntries(entries => {
      entries.forEach(entry => {
        traverseFileTree(entry, files)
      })
    })
  }
}

const buildFolderStructure = (files) => {
  const structure = {}
  
  files.forEach(file => {
    // 从文件路径中提取文件夹信息
    const path = file.webkitRelativePath || file.name
    const pathParts = path.split('/')
    
    if (pathParts.length > 1) {
      // 多级文件夹
      const folderPath = pathParts.slice(0, -1).join('/')
      if (!structure[folderPath]) {
        structure[folderPath] = []
      }
      structure[folderPath].push({
        name: pathParts[pathParts.length - 1],
        fullPath: path,
        file: file
      })
    } else {
      // 根目录文件
      if (!structure['根目录']) {
        structure['根目录'] = []
      }
      structure['根目录'].push({
        name: file.name,
        fullPath: file.name,
        file: file
      })
    }
  })
  
  folderStructure.value = structure
}

const clearFiles = () => {
  fileList.value = []
  folderStructure.value = {}
  activeFolders.value = []
}



const uploadFiles = async () => {
  if (fileList.value.length === 0) {
    ElMessage.warning('请先选择文件')
    return
  }
  
  uploading.value = true
  processingMessage.value = '正在上传文件...'
  processingProgress.value = 10
  
  try {
    // 1. 上传文件
    const formData = new FormData()
    fileList.value.forEach((file, index) => {
      // 确保使用正确的文件对象
      const fileToUpload = file.raw || file
      formData.append('files', fileToUpload)
      
      // 传递文件夹路径信息
      const relativePath = file.webkitRelativePath || file.name
      formData.append(`file_${index}_path`, relativePath)
      
      console.log(`上传文件 ${index + 1}:`, {
        name: file.name,
        size: file.size,
        relativePath: relativePath,
        type: file.type
      })
    })
    
    console.log(`准备上传 ${fileList.value.length} 个文件`)
    processingProgress.value = 20
    
    const uploadResponse = await axios.post('/api/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    
    taskId.value = uploadResponse.data.task_id
    processingProgress.value = 30
    
    // 2. 开始处理
    currentStep.value = 'processing'
    processingMessage.value = '正在进行 OCR 识别...'
    
    await axios.post(`/api/process/${taskId.value}`)
    processingProgress.value = 40
    
    // 3. 轮询状态
    let pollCount = 0
    const checkStatus = async () => {
      pollCount++
      const statusResponse = await axios.get(`/api/status/${taskId.value}`)
      const status = statusResponse.data.status
      
      if (status === 'completed') {
        // 获取结果
        processingProgress.value = 90
        processingMessage.value = '正在整理结果...'
        
        const resultResponse = await axios.get(`/api/result/${taskId.value}`)
        resultData.value = resultResponse.data.result
        
        processingProgress.value = 100
        processingMessage.value = '处理完成！'
        
        setTimeout(() => {
          currentStep.value = 'completed'
          uploading.value = false
          ElMessage.success('处理完成！')
        }, 500)
        
      } else if (status === 'failed') {
        ElMessage.error('处理失败：' + statusResponse.data.message)
        uploading.value = false
        currentStep.value = 'upload'
        processingProgress.value = 0
      } else {
        // 更新进度（基于轮询次数，但不超过85%）
        const progress = Math.min(40 + (pollCount * 3), 85)
        processingProgress.value = progress
        
        // 更新消息
        if (pollCount <= 5) {
          processingMessage.value = '正在识别图片中的文字信息...'
        } else if (pollCount <= 10) {
          processingMessage.value = '正在提取订单号和金额...'
        } else if (pollCount <= 15) {
          processingMessage.value = '正在进行去重处理...'
        } else {
          processingMessage.value = '正在生成最终结果...'
        }
        
        // 继续轮询
        setTimeout(checkStatus, 2000)
      }
    }
    
    checkStatus()
    
  } catch (error) {
    console.error('上传失败:', error)
    ElMessage.error('上传失败：' + (error.response?.data?.error || error.message))
    uploading.value = false
    currentStep.value = 'upload'
  }
}

const downloadResult = async () => {
  downloading.value = true
  try {
    const response = await axios.get(`/api/download/${taskId.value}`, {
      responseType: 'blob'
    })
    
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `去重后的支付截图_${new Date().getTime()}.zip`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    
    ElMessage.success('下载成功！')
  } catch (error) {
    console.error('下载失败:', error)
    ElMessage.error('下载失败：' + (error.response?.data?.error || error.message))
  } finally {
    downloading.value = false
  }
}

const downloadCache = async () => {
  downloading.value = true
  try {
    const response = await axios.get(`/api/cache/${taskId.value}`, {
      responseType: 'blob'
    })
    
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `ocr_cache_${taskId.value}.json`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    
    ElMessage.success('缓存文件下载成功！')
  } catch (error) {
    console.error('下载缓存失败:', error)
    ElMessage.error('下载缓存失败：' + (error.response?.data?.error || error.message))
  } finally {
    downloading.value = false
  }
}

const resetAll = async () => {
  // 清理任务
  if (taskId.value) {
    try {
      await axios.delete(`/api/cleanup/${taskId.value}`)
    } catch (error) {
      console.error('清理失败:', error)
    }
  }
  
  currentStep.value = 'upload'
  fileList.value = []
  taskId.value = null
  resultData.value = {}
  activeTab.value = 'orders'
  activeDuplicates.value = []
  activeFolders.value = []
  folderStructure.value = {}
  processingProgress.value = 0
  processingMessage.value = '正在上传文件...'
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
}

#app {
  min-height: 100vh;
}

.el-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.el-header {
  background: white;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 30px 20px;
}

.header-content {
  text-align: center;
}

.header-content h1 {
  font-size: 28px;
  color: #303133;
  margin-bottom: 8px;
}

.subtitle {
  color: #909399;
  font-size: 14px;
}

.el-main {
  flex: 1;
  padding: 40px 20px;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
}

.upload-card,
.processing-card,
.result-card {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 18px;
  font-weight: bold;
}

.upload-demo {
  margin-bottom: 20px;
}

.upload-actions {
  text-align: center;
  padding-top: 20px;
}

.processing-content {
  padding: 40px;
  text-align: center;
}

.processing-content .el-progress {
  margin-bottom: 20px;
}

.processing-text {
  margin: 20px 0 10px;
  font-size: 18px;
  font-weight: bold;
  color: #409eff;
}

.processing-tip {
  color: #909399;
  font-size: 14px;
}

.result-summary {
  margin-bottom: 30px;
}

.result-tabs {
  margin-top: 20px;
}

.result-actions {
  text-align: center;
  margin-top: 30px;
}

.duplicate-title {
  display: flex;
  align-items: center;
  gap: 15px;
  width: 100%;
}

.duplicate-title .order-num {
  font-family: monospace;
  font-size: 14px;
}

.duplicate-title .amount {
  margin-left: auto;
  font-weight: bold;
  color: #67c23a;
}

.duplicate-content {
  padding: 15px;
  background: #f5f7fa;
  border-radius: 4px;
}

.duplicate-content p {
  margin-bottom: 10px;
}

.duplicate-content ul {
  margin-left: 20px;
  margin-top: 5px;
}

.duplicate-content li {
  margin-bottom: 5px;
  color: #606266;
}

.el-footer {
  background: white;
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  height: 60px !important;
}

.footer-content {
  text-align: center;
  color: #909399;
  font-size: 14px;
}

.folder-preview {
  margin-top: 20px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid #e9ecef;
}

.folder-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.file-tag {
  margin: 2px;
}

.upload-options {
  margin-top: 15px;
  text-align: center;
}

.folder-upload-area {
  margin-bottom: 20px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.folder-upload-area:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.manual-folder-select {
  margin-top: 20px;
  text-align: center;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid #e9ecef;
}

.folder-tip {
  display: block;
  margin-top: 8px;
  color: #6c757d;
  font-size: 12px;
}

.duplicate-images-title {
  display: flex;
  align-items: center;
  gap: 15px;
  width: 100%;
}

.duplicate-group-title {
  font-weight: bold;
}

.duplicate-images-content {
  padding: 15px;
  background: #f5f7fa;
  border-radius: 4px;
}

.duplicate-files-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.duplicate-file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: white;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
}

.duplicate-file-item .file-name {
  flex: 1;
  font-family: monospace;
  font-size: 14px;
}
</style>

