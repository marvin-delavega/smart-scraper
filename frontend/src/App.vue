<template>
  <v-app>
    <v-main>
      <v-container>
        <v-card class="mb-6">
          <v-card-item>
            <v-card-title class="text-headline-small">SmartScrape Dashboard</v-card-title>
            <v-card-subtitle>Updated 20 minutes ago</v-card-subtitle>
          </v-card-item>
        </v-card>

        <v-row class="mb-6">
          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-briefcase-outline" append-icon="mdi-trending-up">
              <v-card-title class="text-title-small text-uppercase text-grey ">Jobs Scraped</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ totalJobsScraped }}</v-card-text>
              <v-card-text class="text-green font-weight-medium pt-0">{{ totalJobsScrapedComparison }} since last run</v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-text-box-search-outline" append-icon="mdi-trending-up">
              <v-card-title class="text-title-small text-uppercase text-grey ">Characters Parsed</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ totalJobsScraped }}</v-card-text>
              <v-card-text class="text-green font-weight-medium pt-0">{{ totalJobsScrapedComparison }} since last run</v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-clock-outline" append-icon="mdi-trending-up">
              <v-card-title class="text-title-small text-uppercase text-grey ">Total Runtime</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ totalJobsScraped }}</v-card-text>
              <v-card-text class="text-green font-weight-medium pt-0">{{ totalJobsScrapedComparison }} since last run</v-card-text>
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
const totalJobsScraped = ref(100)
const totalJobsScrapedComparison = ref('+8.5%')

const currentPage = ref(1)
const jobsPerPage = ref(10)
const totalPages = ref(1)
const totalJobs = ref(0)
const expandedItemId = ref<number | null>(null)
const overflowIndexList = ref<number[]>([])
const isLoading = ref(true)

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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

onMounted(async () => {
  const {count, error} = await supabase.from('job').select('*', {count: 'exact', head: true})

  if (error) {
    console.log(error)
    return
  }

  totalJobs.value = count ?? 0
  totalPages.value = Math.ceil((count ?? 0) / jobsPerPage.value)

  await fetchJobs()
})
</script>
