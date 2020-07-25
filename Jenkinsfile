pipeline {
  environment {
    PROJECT = "sandfox"
    APP_NAME = "iris-app"
    SVC_NAME = "${APP_NAME}-service"
    CLUSTER = "iris-cluster"
    CLUSTER_ZONE = "us-east1-d"
    IMAGE_TAG = "gcr.io/${PROJECT}/${APP_NAME}:v${env.BUILD_NUMBER}"
    JENKINS_CRED = "${PROJECT}"
  }
  agent {
    kubernetes {
      label 'iris-app'
      defaultContainer 'jnlp'
      yaml """
apiVersion: v1
kind: Pod
metadata:
labels:
  component: ci
spec:
  serviceAccountName: jenkins-server
  containers:
  - name: gcloud
    image: gcr.io/cloud-builders/gcloud
    command:
    - cat
    tty: true
  - name: kubectl
    image: gcr.io/cloud-builders/kubectl
    command:
    - cat
    tty: true
"""
    }
  }
  stages {
    stage('Build Image') {
      steps {
        container('gcloud') {
          sh "PYTHONUNBUFFERED=1 gcloud builds submit -t ${IMAGE_TAG} ."
        }
      }
    }
    stage('Deploy Image') {
      when { branch 'master' }
      steps{
        container('kubectl') {
          sh("sed -i.bak 's#gcr.io/sandfox/iris-app:v3#${IMAGE_TAG}#' k8s/deployments/deployment.yaml")
          step([$class: 'KubernetesEngineBuilder', projectId: env.PROJECT, clusterName: env.CLUSTER, zone: env.CLUSTER_ZONE, manifestPattern: 'k8s/services', credentialsId: env.JENKINS_CRED, verifyDeployments: false])
          step([$class: 'KubernetesEngineBuilder', projectId: env.PROJECT, clusterName: env.CLUSTER, zone: env.CLUSTER_ZONE, manifestPattern: 'k8s/deployments', credentialsId: env.JENKINS_CRED, verifyDeployments: true])
          sh("echo http://`kubectl get service/${SVC_NAME} -o jsonpath='{.status.loadBalancer.ingress[0].ip}'` > ${SVC_NAME}")
        }
      }
    }
  }
}
