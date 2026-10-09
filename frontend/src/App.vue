<template>
  <v-app>
    <v-main>
      <v-container>
        <v-card class="mb-6">
          <v-card-item>
            <v-card-title class="text-headline-small">SmartScrape Dashboard</v-card-title>
            <v-card-subtitle>Updated {{ lastUpdate }}</v-card-subtitle>
          </v-card-item>
        </v-card>

        <v-row class="mb-6">
          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-briefcase-outline">
              <v-card-title class="text-title-small text-uppercase text-grey ">Jobs Scraped</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ analytics?.total_saved_jobs ?? 0 }}</v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-text-box-search-outline">
              <v-card-title class="text-title-small text-uppercase text-grey ">Characters Parsed</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ analytics?.total_parsed_chars ?? 0 }}</v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-clock-outline">
              <v-card-title class="text-title-small text-uppercase text-grey ">Total Runtime</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ getFormattedTime(analytics?.total_runtime?.toString() ?? '0') }}</v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <v-card>
          <v-card-title class="flex-grow text-title-medium">Scraped Job Listing | {{ totalJobs }} jobs</v-card-title>
          <v-divider></v-divider>
          <v-pagination 
            class="text-body-small" 
            :show-first-last-page="true" 
            size="small"
            v-model="currentPage"
            :length="totalPages"
            :total-visible="5"
            :disabled="isLoading"
            @update:model-value="fetchJobs"></v-pagination>
          <v-skeleton-loader type="list-item-three-line" v-show="isLoading"></v-skeleton-loader>
          <v-list v-show="!isLoading" class="ml-4 mr-4">
            <v-list-item 
              v-for="(job, index) in jobs" 
              :ref="(el) => checkOverflow(el, index)" 
              :key="index" 
              @click="openJobLink(job.primary_link)"
              class="mb-3 border elevation-1 rounded bg-surface">
              <div class="d-flex flex-col">
                <v-img :src="getIconUrl(job.website_address)" max-width="24" max-height="24" class="my-auto mr-3"></v-img>
                <div>
                  <v-list-item-title>{{ job.title }}</v-list-item-title>
                  <v-list-item-subtitle>{{ getDomain(job.website_address) + ' | ' + job.company + ' | ' + job.location }}</v-list-item-subtitle>
                </div>
              </div>
              <v-divider class="mt-2 mb-4"></v-divider>
              <p class="text-body-medium">Salary: <span class="text-green">{{ job.salary_range || 'Not available'}}</span></p>
              <v-sheet
                :max-height="expandedItemId != index ? '200px' : ''" 
                class="overflow-y-hidden job-body">
                <p class="text-body-medium text-grey-lighten-1">{{ job.desc }}</p>
                <p class="text-body-medium mt-6">Relevant links:</p>
                <v-btn 
                  v-for="(link, index) in job.links"
                  :href="link"
                  target="_blank"
                  variant="text"
                  class="text-body-small text-truncate justify-start text-decoration-underline text-grey-lighten-1"
                  max-width="100%">
                  {{ link }}
                </v-btn>
              </v-sheet>
              <v-btn 
                v-if="overflowIndexList.includes(index) && expandedItemId !== index"
                class="text-body-small text-grey my-2 see-more-button" 
                variant="text"
                @click.stop="expandedItemId=index">
                See more
              </v-btn>
            </v-list-item>
          </v-list>
        </v-card>
      </v-container>
    </v-main>
  </v-app>
</template>

<script lang="ts" setup>
import { onMounted, ref } from 'vue';
import { supabase } from './lib/supabaseClient';

type Analytics = {
  total_crawled_chars: number
  total_runtime:number
  total_retries: number
  total_parsed_chars: number
  total_saved_jobs: number
  total_skipped_chunks: number
}

const analytics = ref<Analytics>()

type Job = {
  title: string
  desc: string
  company: string
  salary_range: string
  location: string
  links: string[]
  website_address: string
  primary_link: string
  content_hash: string
}

const jobs = ref<Job[]>()

const currentPage = ref(1)
const jobsPerPage = ref(10)
const totalPages = ref(1)
const totalJobs = ref(0)
const expandedItemId = ref<number | null>(null)
const overflowIndexList = ref<number[]>([])
const isLoading = ref(true)
const lastUpdate = ref('')

const getIconUrl = (url: string): string => {
  if (url === '')
    return ''

  return 'https://icons.duckduckgo.com/ip3/' + getDomain(url) + '.ico'
}

const getDomain = (url: string): string => {
  return new URL(url).hostname
}

const openJobLink = (url: string) => {
  if (url === '')
    return 

  window.open(url, '_blank');
}

const timeRegex = /^\d{1,2}:\d{2}:\d{2}\.\d+$/;

const getFormattedTime = (time: string): string => {
  if (!timeRegex.test(time)) {
    console.log('Invalid time ' + time)
    return time
  }

  const segments = time.split(':')
  const hr = Number(segments[0]) > 0 ? segments[0] + ' hr' : ''
  const min = Number(segments[1]) > 0 ? segments[1] + ' min' : ''
  const sec = Number(segments[2]) > 0 ? Math.ceil(Number(segments[2])) + ' sec' : ''

  return `${hr} ${min} ${sec}`
}

const checkOverflow = (el: any, index: number) => {
  if (overflowIndexList.value.includes(index))
    return

  const listItem = el.$el as HTMLDivElement | null

  if (listItem === null) {
    return
  }

  const body = listItem.getElementsByClassName('job-body')[0]
  if (body.clientHeight < body.scrollHeight)
    overflowIndexList.value.push(index)

  console.log(overflowIndexList.value)
}

const fetchAnalytics = async () => {
  const {data, error} = await supabase.from('run_analytics').select()

  if (error) {
    console.log(error)
    return
  }

  analytics.value = data[0] as Analytics
}

const fetchJobs = async () => {
  isLoading.value = true
  const from = (currentPage.value - 1) * jobsPerPage.value
  const to = from + jobsPerPage.value
  const {data, error: fetchError } = await supabase.from('job').select().range(from, to);
  
  if (fetchError){
    console.log(fetchError.message)
    return
  }

  jobs.value = data as Job[]
  overflowIndexList.value = []
  isLoading.value = false
}

const fetchLastUpdate = async () => {
  const {data, error} = await supabase.from('scrape_run').select('end_at').order('end_at', {ascending: false}).limit(1)
  
  if (error) {
    console.log(error)
    return
  }

  const dateUpdated = new Date(data[0].end_at)
  const timeSinceUpdate = Date.now() - dateUpdated.getTime()

  console.log(dateUpdated)
  console.log(timeSinceUpdate)

  let hours = timeSinceUpdate / 1000 / 60 / 60
  let minutes = (hours % 1) * 60
  let seconds = (minutes % 1) * 60

  hours = Math.floor(hours)
  minutes = Math.floor(minutes)
  seconds = Math.floor(seconds)

  if (hours >= 48) {
    lastUpdate.value = (hours / 24) + ' days ago'
  } else if (hours >= 24 && hours < 48) {
    lastUpdate.value = '1 day ago'
  } else {
    lastUpdate.value = `${hours > 0 ? hours + ' hr ' : ''}${minutes > 0 ? minutes + ' min ' : ''}${seconds > 0 ? seconds + ' sec' : ''} ago`
  }
}

onMounted(async () => {
  const {count, error} = await supabase.from('job').select('*', {count: 'exact', head: true})

  if (error) {
    console.log(error)
    return
  }

  totalJobs.value = count ?? 0
  totalPages.value = Math.ceil((count ?? 0) / jobsPerPage.value)

  await fetchLastUpdate()
  await fetchAnalytics()
  await fetchJobs()
})
</script>
