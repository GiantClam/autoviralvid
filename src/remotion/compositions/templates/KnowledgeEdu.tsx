import React from 'react';
import VideoTemplate, { VideoTemplateProps } from '../VideoTemplate';

export default function KnowledgeEdu(props: VideoTemplateProps) {
  return (
    <VideoTemplate
      {...props}
      transition="fade"
      style={{
        ...props.style,
        primaryColor: '#4ECDC4',
        titleFontSize: 48,
        subtitleFontSize: 26,
      }}
    />
  );
}
