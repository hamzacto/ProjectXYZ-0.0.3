import axios from "axios";
import { FileCategory, FileItem } from "../templatesModal/components/GuidedAgentkhowledgeBase/types";

const axiosInstance = axios.create({
    baseURL: 'http://localhost:3000/api/v1', 
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: 120000,
  });
export async function insertFile(file: any, collectionName: string) {
    let base64Content: string | undefined;

    if (file.content instanceof ArrayBuffer) {
        base64Content = btoa(
            String.fromCharCode(...Array.from(new Uint8Array(file.content)))
        );
    } else if (
        typeof file.content === 'string' &&
        file.content.startsWith('data:application/pdf;base64,')
    ) {
        base64Content = file.content.split(',')[1];
    } else {
        console.error('Invalid file content format for', file.name);
        return;
    }

    if (!base64Content) {
        console.error('No content found for', file.name);
        return;
    }
    function isValidBase64(base64String: string): boolean {
        const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/;
        return base64String.length % 4 === 0 && base64Regex.test(base64String);
    }
    if (!isValidBase64(base64Content)) {
        console.error('Invalid Base64 content detected for', file.name);
        return;
    }

    const payload = {
        id: file.id,
        name: file.name,
        size: file.size,
        type: file.type,
        category: file.category,
        content: base64Content,
        file_path: file.file_path,
        collection_name: collectionName,
        batch_size: 50,
        chunk_size: 512,
        chunk_overlap: 200,
    };

    try {
        const { data } = await axiosInstance.post('/milvus/insert_file', payload);
        const taskId = data.task_id;
        console.log(`Task ${taskId} started for file ${file.name}`);

        // Poll for status updates
        const pollStatus = async () => {
            try {
                const { data: status } = await axiosInstance.get(`/milvus/task/${taskId}`);
                // Update UI progress if available
                if (status.total_chunks > 0) {
                    const progress = (status.processed_chunks / status.total_chunks) * 100;
                    updateFileProgress(file.id, progress);
                }
                if (status.status === 'completed') {
                    console.log(`File ${file.name} processing completed`);
                    updateFileStatus(file.id, 'completed');
                    return;
                } else if (status.status === 'failed') {
                    console.error(`File ${file.name} processing failed:`, status.error);
                    updateFileStatus(file.id, 'failed', status.error);
                    return;
                }
                // Poll again after a delay
                setTimeout(pollStatus, 1000);
            } catch (error: any) {
                console.error(`Error checking status for ${file.name}:`, error);
                updateFileStatus(file.id, 'failed', error.message);
            }
        };
        pollStatus();
    } catch (error) {
        console.error(`Error inserting file ${file.name}:`, error);
    }
}
// Helper functions for UI updates
function updateFileProgress(fileId: string, progress: number) {
    const progressElement = document.querySelector(`[data-file-id="${fileId}"] .progress`) as HTMLElement;
    if (progressElement) {
        progressElement.style.width = `${progress}%`;
    }
}

function updateFileStatus(fileId: string, status: 'completed' | 'failed', error?: string) {
    const statusElement = document.querySelector(`[data-file-id="${fileId}"] .status`);
    if (statusElement) {
        statusElement.textContent = status;
        if (error) {
            statusElement.setAttribute('title', error);
        }
    }
}

export async function insertFilesIntoDatabase(fileCategories: FileCategory[], collectionName: string) {
    const files: FileItem[] = [];
    fileCategories.forEach((cat) => {
        files.push(...cat.files);
    });
    // Process files with a concurrency limit of 4 (adjust as needed)
    await processInBatches(files, (file) => insertFile(file, collectionName), 4);
}

// A simple concurrency limiter
export async function processInBatches<T>(items: T[], handler: (item: T) => Promise<void>, concurrency: number = 4) {
    const executing: Promise<void>[] = [];
    const settled = new Map<Promise<void>, boolean>();

    for (const item of items) {
        const p = handler(item).then(() => {
            settled.set(p, true);
        });
        executing.push(p);
        if (executing.length >= concurrency) {
            await Promise.race(executing);
            // Remove resolved promises
            executing.splice(0, executing.length, ...executing.filter(p => !settled.get(p)));
        }
    }
    await Promise.all(executing);
}

export async function deleteFileFromDatabase(fileId: string, collectionName: string) {
    try {
        // Call the backend API to delete the file from Milvus
        const { data } = await axiosInstance.delete(`/milvus/files/${collectionName}/${fileId}`);
        console.log(`File ${fileId} deleted from collection ${collectionName}:`, data);
        return true;
    } catch (error) {
        console.error(`Error deleting file ${fileId} from collection ${collectionName}:`, error);
        return false;
    }
}

