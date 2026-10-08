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
          <v-card-title class="text-title-small">Scraped Job Listing</v-card-title>
          <v-list class="ml-4 mr-4">
            <v-list-item 
              v-for="(job, index) in jobs" 
              :key="index" 
              :href="job.primary_link"
              class="mb-3 border elevation-1 rounded bg-surface">
              <div class="d-flex flex-col">
                <v-img :src="getIconUrl(job)" max-width="24" max-height="24" class="my-auto mr-3"></v-img>
                <div>
                  <v-list-item-title>{{ job.title }}</v-list-item-title>
                  <v-list-item-subtitle>{{ getDomain(job) + ' | ' + job.company + ' | ' + job.location }}</v-list-item-subtitle>
                </div>
              </div>
              <v-divider class="mt-2 mb-4"></v-divider>
              <p class="text-body-medium">Salary Range: {{ job.salary_range || 'Not available'}}</p>
              <p class="text-body-medium">{{ job.desc }}</p>
              <p class="text-body-medium mt-6">Relevant links:</p>
              <v-btn 
                v-for="(link, index) in job.links"
                :href="link"
                target="_blank"
                variant="text"
                class="px-0 ml-2 text-body-small text-truncate justify-start"
                max-width="100%">
                {{ link }}
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
const jobs = ref<Job[]>();
const totalJobsScraped = ref(100);
const totalJobsScrapedComparison = ref('+8.5%');

function getIconUrl(job: Job): string {
  return 'https://' + getDomain(job) + '/favicon.ico'
}

function getDomain(job: Job): string {
  return new URL(job.website_address).hostname
}

onMounted(async () => {
  const {data, error: fetchError } = await supabase.from('job').select();
  
  if (fetchError)
    console.log(fetchError.message)

  jobs.value = data as Job[]
})
</script>
