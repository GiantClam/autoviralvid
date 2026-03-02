import { VideoProject, ItemType, Asset } from './lib/types';

export const INITIAL_PROJECT: VideoProject = {
    name: 'Untitled Project',
    width: 1280,
    height: 720,
    fps: 30,
    duration: 15,
    backgroundColor: '#000000',
    tracks: [
        {
            id: 1,
            type: 'video',
            name: 'Main Track',
            items: [
                {
                    id: 'clip-1',
                    type: ItemType.VIDEO,
                    content: 'https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4',
                    startTime: 0,
                    duration: 5,
                    trackId: 1,
                    name: 'Intro Clip',
                    style: { scale: 100, opacity: 1, x: 50, y: 50, rotation: 0 }
                }
            ]
        },
        {
            id: 2,
            type: 'overlay',
            name: 'Text Overlay',
            items: [
                {
                    id: 'text-1',
                    type: ItemType.TEXT,
                    content: 'Welcome to AutoViralVid',
                    startTime: 0.5,
                    duration: 4,
                    trackId: 2,
                    name: 'Title',
                    style: {
                        color: '#ffffff',
                        fontSize: 48,
                        x: 50,
                        y: 80,
                        scale: 100,
                        opacity: 1,
                        rotation: 0
                    }
                }
            ]
        },
        {
            id: 3,
            type: 'audio',
            name: 'Background Music',
            items: []
        }
    ]
};

export const INITIAL_ASSETS: Asset[] = [
    {
        id: 'asset-1',
        type: ItemType.VIDEO,
        name: 'Big Buck Bunny',
        url: 'https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4',
        thumbnail: 'https://storage.googleapis.com/gtv-videos-bucket/sample/images/BigBuckBunny.jpg'
    },
    {
        id: 'asset-2',
        type: ItemType.VIDEO,
        name: 'Elephants Dream',
        url: 'https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4',
        thumbnail: 'https://storage.googleapis.com/gtv-videos-bucket/sample/images/ElephantsDream.jpg'
    },
    {
        id: 'asset-3',
        type: ItemType.IMAGE,
        name: 'Mountain Landscape',
        url: 'https://picsum.photos/id/10/1280/720',
        thumbnail: 'https://picsum.photos/id/10/200/200'
    }
];
